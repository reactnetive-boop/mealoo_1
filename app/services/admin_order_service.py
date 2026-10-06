"""
Admin operations on orders.

Forced status changes go through the same state machine as everyone else
(actor "admin") and carry their money effects: forcing 'delivered' settles
the kitchen / partner / platform once, forcing 'cancelled' refunds the
customer once. Every forced change needs a reason and is audited.

Delivery partners are assigned per order, or for a whole subscription
(app/domain/delivery_assignment.py), in which case every open meal and every
meal generated later goes to that partner.
"""

from datetime import date

from sqlalchemy import or_, cast, String
from sqlalchemy.orm import Session

from app.core.audit import record_audit, business_event
from app.core.clock import now_utc, today_local
from app.core.config import DELIVERY_CODE_MAX_ATTEMPTS, PICKUP_CODE_MAX_ATTEMPTS
from app.core.errors import DomainError
from app.domain import capacity, checkout, notify, partner_leave
from app.domain import delivery_assignment
from app.domain import orders as meals
from app.domain.eligibility import is_on_holiday, kitchen_serves, parse_pincode, provider_block_reason
from app.domain.slots import SLOTS, is_before_cutoff
from app.domain.status import (
    assert_sub_order_transition,
    assert_extra_order_transition,
    SUB_ORDER_STATUSES,
    EXTRA_ORDER_STATUSES,
    SUBSCRIPTION_STATUSES,
    SUB_UNPICKED_STATUSES,
    EXTRA_UNPICKED_STATUSES,
    IN_HAND_STATUSES,
)
from app.models.admin_user_model import AdminUser
from app.models.delivery_boy_model import DeliveryBoy
from app.models.extra_order_model import ExtraOrder
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.subscription_delivery_assignment_model import SubscriptionDeliveryAssignment
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.subscription_plan_model import SubscriptionPlan
from app.models.user_address_model import UserAddress
from app.models.user_model import User
from app.services.admin_views import (
    order_admin_view, extra_order_admin_view, subscription_admin_view, address_view,
)

SUB_ASSIGNABLE = SUB_UNPICKED_STATUSES
EXTRA_ASSIGNABLE = EXTRA_UNPICKED_STATUSES
_SLOT_RANK = {slot: i for i, slot in enumerate(SLOTS)}


def _sub_order(db: Session, order_id) -> Order:
    order = db.query(Order).filter(Order.order_id == order_id).with_for_update().first()
    if not order:
        raise DomainError("Subscription order not found", 404)
    return order


def _extra_order(db: Session, order_id) -> ExtraOrder:
    order = db.query(ExtraOrder).filter(ExtraOrder.extra_order_id == order_id).with_for_update().first()
    if not order:
        raise DomainError("Extra order not found", 404)
    return order


def _partner(db: Session, delivery_boy_id) -> DeliveryBoy:
    boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == delivery_boy_id).first()
    if not boy:
        raise DomainError("Delivery partner not found", 404)
    if not boy.is_active or boy.approval_status != "approved":
        raise DomainError("This delivery partner is not active and approved")
    return boy


def _check_status_filter(status: str | None, allowed) -> None:
    if status and status not in allowed:
        raise DomainError(f"status must be one of: {', '.join(allowed)}")


def _lookup(db: Session, model, key: str, ids) -> dict:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {getattr(r, key): r for r in db.query(model).filter(getattr(model, key).in_(ids))}


def _locked_subscription(db: Session, subscription_id) -> Subscription:
    sub = db.query(Subscription).filter(Subscription.subscription_id == subscription_id).with_for_update().first()
    if sub is None:
        raise DomainError("Subscription not found", 404)
    return sub


def _partner_brief(boy: DeliveryBoy | None, provider_id=None) -> dict | None:
    if boy is None:
        return None
    return {
        "delivery_boy_id": boy.delivery_boy_id,
        "full_name": boy.full_name,
        "mobile_number": boy.mobile_number,
        "vehicle_type": boy.vehicle_type,
        "vehicle_number": boy.vehicle_number,
        "is_active": bool(boy.is_active),
        "is_online": bool(boy.is_online),
        "approval_status": boy.approval_status,
        "assigned_provider_reference_id": boy.assigned_provider_reference_id,
        # why new meals would NOT go to this partner (None = they will)
        "block_reason": delivery_assignment.partner_block_reason(boy, provider_id) if provider_id else None,
    }


def _new_kitchen(db: Session, new_provider_id: str, current_provider_id, on: date, slot: str, address_id) -> Provider:
    if str(current_provider_id) == new_provider_id:
        raise DomainError("New provider is the same as the current provider.")
    provider = db.query(Provider).filter(Provider.provider_id == new_provider_id).with_for_update().first()
    if provider is None:
        raise DomainError("New provider not found", 404)
    reason = provider_block_reason(provider)
    if reason:
        raise DomainError(f"New kitchen cannot take orders: {reason}")
    if is_on_holiday(db, provider.provider_id, on):
        raise DomainError(f"New kitchen is on holiday on {on}.")
    address = db.query(UserAddress).filter(UserAddress.user_address_id == address_id).first()
    if address is not None and not kitchen_serves(db, provider, parse_pincode(address.pin_code)):
        raise DomainError("New kitchen does not deliver to this customer's pincode.")
    if not is_before_cutoff(on, slot):
        raise DomainError(f"The {slot} cut-off for {on} has passed; the order can no longer be moved.")
    return provider


def _assignment_filter(query, model, delivery_boy_id, assignment, open_statuses):
    if assignment and assignment not in ("assigned", "unassigned"):
        raise DomainError("assignment must be 'assigned' or 'unassigned'")
    if delivery_boy_id:
        query = query.filter(model.delivery_boy_reference_id == delivery_boy_id)
    if assignment == "assigned":
        query = query.filter(model.delivery_boy_reference_id.isnot(None))
    elif assignment == "unassigned":
        # only orders that still need a partner
        query = query.filter(model.delivery_boy_reference_id.is_(None), model.status.in_(open_statuses))
    return query


def _with_names(db: Session, orders, views: list) -> list:
    """Customer, kitchen and partner names for a page of orders (three queries)."""
    def names(model, id_col, name_col, ids):
        ids = {i for i in ids if i}
        return dict(db.query(id_col, name_col).filter(id_col.in_(ids)).all()) if ids else {}

    users = names(User, User.user_id, User.full_name, (o.user_reference_id for o in orders))
    kitchens = names(Provider, Provider.provider_id, Provider.business_name, (o.vendor_reference_id for o in orders))
    partners = names(DeliveryBoy, DeliveryBoy.delivery_boy_id, DeliveryBoy.full_name,
                     (o.delivery_boy_reference_id for o in orders))
    for view in views:
        view["customer_name"] = users.get(view["user_reference_id"])
        view["vendor_name"] = kitchens.get(view["vendor_reference_id"])
        view["delivery_boy_name"] = partners.get(view["delivery_boy_reference_id"])
    return views


class AdminOrderService:

    # ── Lists ─────────────────────────────────────────────

    @staticmethod
    def list_subscription_orders(db: Session, vendor_id: str = None, user_id: str = None,
                                 order_date: date = None, status: str = None,
                                 page: int = 1, limit: int = 50,
                                 delivery_boy_id: str = None, assignment: str = None):
        _check_status_filter(status, SUB_ORDER_STATUSES)
        query = _assignment_filter(db.query(Order), Order, delivery_boy_id, assignment, SUB_ASSIGNABLE)
        if vendor_id:
            query = query.filter(Order.vendor_reference_id == vendor_id)
        if user_id:
            query = query.filter(Order.user_reference_id == user_id)
        if order_date:
            query = query.filter(Order.order_date == order_date)
        if status:
            query = query.filter(Order.status == status)

        total = query.count()
        orders = query.order_by(Order.order_date.desc(), Order.meal_slot).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page,
                "orders": _with_names(db, orders, [order_admin_view(o) for o in orders])}

    @staticmethod
    def list_extra_orders(db: Session, vendor_id: str = None, user_id: str = None,
                          delivery_date: date = None, status: str = None,
                          page: int = 1, limit: int = 50,
                          delivery_boy_id: str = None, assignment: str = None):
        _check_status_filter(status, EXTRA_ORDER_STATUSES)
        query = _assignment_filter(db.query(ExtraOrder), ExtraOrder, delivery_boy_id, assignment, EXTRA_ASSIGNABLE)
        if vendor_id:
            query = query.filter(ExtraOrder.vendor_reference_id == vendor_id)
        if user_id:
            query = query.filter(ExtraOrder.user_reference_id == user_id)
        if delivery_date:
            query = query.filter(ExtraOrder.delivery_date == delivery_date)
        if status:
            query = query.filter(ExtraOrder.status == status)

        total = query.count()
        orders = query.order_by(ExtraOrder.delivery_date.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page,
                "orders": _with_names(db, orders, [extra_order_admin_view(o) for o in orders])}

    @staticmethod
    def list_subscriptions(db: Session, vendor_id: str = None, user_id: str = None,
                           status: str = None, page: int = 1, limit: int = 20,
                           delivery_boy_id: str = None, assignment: str = None, search: str = None):
        _check_status_filter(status, SUBSCRIPTION_STATUSES)
        if assignment and assignment not in ("assigned", "unassigned"):
            raise DomainError("assignment must be 'assigned' or 'unassigned'")
        query = db.query(Subscription)
        if vendor_id:
            query = query.filter(Subscription.vendor_reference_id == vendor_id)
        if user_id:
            query = query.filter(Subscription.user_reference_id == user_id)
        if status:
            query = query.filter(Subscription.status == status)
        if delivery_boy_id:
            query = query.filter(Subscription.delivery_boy_reference_id == delivery_boy_id)
        if assignment == "assigned":
            query = query.filter(Subscription.delivery_boy_reference_id.isnot(None))
        elif assignment == "unassigned":
            query = query.filter(Subscription.delivery_boy_reference_id.is_(None))
        if search:
            pattern = f"%{search.strip()}%"
            query = (
                query.join(User, User.user_id == Subscription.user_reference_id)
                .join(Provider, Provider.provider_id == Subscription.vendor_reference_id)
                .filter(or_(
                    User.full_name.ilike(pattern),
                    User.phone.ilike(pattern),
                    Provider.business_name.ilike(pattern),
                    cast(Subscription.subscription_id, String).ilike(f"{search.strip()}%"),
                ))
            )

        total = query.count()
        subs = query.order_by(Subscription.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        users = _lookup(db, User, "user_id", (s.user_reference_id for s in subs))
        kitchens = _lookup(db, Provider, "provider_id", (s.vendor_reference_id for s in subs))
        boys = _lookup(db, DeliveryBoy, "delivery_boy_id", (s.delivery_boy_reference_id for s in subs))
        rows = []
        for s in subs:
            user = users.get(s.user_reference_id)
            kitchen = kitchens.get(s.vendor_reference_id)
            boy = boys.get(s.delivery_boy_reference_id)
            rows.append({
                **subscription_admin_view(s),
                "customer_name": user.full_name if user else None,
                "customer_phone": user.phone if user else None,
                "vendor_name": kitchen.business_name if kitchen else None,
                "delivery_boy_name": (boy.full_name or boy.mobile_number) if boy else None,
            })
        return {"success": True, "total": total, "page": page, "subscriptions": rows}

    @staticmethod
    def get_subscription_detail(db: Session, subscription_id: str):
        sub = db.query(Subscription).filter(Subscription.subscription_id == subscription_id).first()
        if sub is None:
            raise DomainError("Subscription not found", 404)

        user = db.query(User).filter(User.user_id == sub.user_reference_id).first()
        kitchen = db.query(Provider).filter(Provider.provider_id == sub.vendor_reference_id).first()
        address = db.query(UserAddress).filter(UserAddress.user_address_id == sub.user_address_reference_id).first()
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.subscription_plan_id == sub.plan_reference_id).first()
        packages = [
            {"package_id": mp.package_id, "package_name": mp.package_name, "quantity": sp.quantity, "unit_price": sp.unit_price}
            for sp, mp in (
                db.query(SubscriptionPackage, MenuPackage)
                .join(MenuPackage, MenuPackage.package_id == SubscriptionPackage.package_reference_id)
                .filter(SubscriptionPackage.subscription_reference_id == sub.subscription_id)
            )
        ]
        orders = db.query(Order).filter(Order.subscription_reference_id == sub.subscription_id).all()
        orders.sort(key=lambda o: (o.order_date, _SLOT_RANK.get(o.meal_slot, 9)))
        history = (
            db.query(SubscriptionDeliveryAssignment)
            .filter(SubscriptionDeliveryAssignment.subscription_reference_id == sub.subscription_id)
            .order_by(SubscriptionDeliveryAssignment.assigned_at.desc())
            .all()
        )
        boys = _lookup(
            db, DeliveryBoy, "delivery_boy_id",
            [o.delivery_boy_reference_id for o in orders] + [h.delivery_boy_reference_id for h in history]
            + [sub.delivery_boy_reference_id],
        )
        admins = _lookup(db, AdminUser, "admin_user_id", [h.assigned_by for h in history] + [h.ended_by for h in history])

        today = today_local()
        current = sub.delivery_boy_reference_id
        stats = {
            "total": len(orders), "completed": 0, "pending": 0, "in_progress": 0, "cancelled": 0, "skipped": 0,
            "missed": 0, "failed": 0, "delivery_assigned": 0, "unassigned_open": 0, "assigned_to_current": 0,
        }
        order_rows = []
        for o in orders:
            open_ = o.status in SUB_UNPICKED_STATUSES and o.order_date >= today
            if o.status == "delivered":
                stats["completed"] += 1
            elif o.status == "cancelled":
                stats["cancelled"] += 1
            elif o.status == "skipped":
                stats["skipped"] += 1
            elif o.status in IN_HAND_STATUSES:
                stats["in_progress"] += 1
            elif open_:
                stats["pending"] += 1
            else:
                stats["missed"] += 1
            if o.status not in ("delivered", "cancelled", "skipped") and (
                (o.pickup_code_attempts or 0) >= PICKUP_CODE_MAX_ATTEMPTS
                or (o.delivery_code_attempts or 0) >= DELIVERY_CODE_MAX_ATTEMPTS
            ):
                stats["failed"] += 1
            if open_ or o.status in IN_HAND_STATUSES:
                if o.delivery_boy_reference_id:
                    stats["delivery_assigned"] += 1
                else:
                    stats["unassigned_open"] += 1
                if current and str(o.delivery_boy_reference_id) == str(current):
                    stats["assigned_to_current"] += 1
            boy = boys.get(o.delivery_boy_reference_id)
            order_rows.append({
                **order_admin_view(o),
                "delivery_boy_name": (boy.full_name or boy.mobile_number) if boy else None,
                "pickup_locked": (o.pickup_code_attempts or 0) >= PICKUP_CODE_MAX_ATTEMPTS,
                "delivery_locked": (o.delivery_code_attempts or 0) >= DELIVERY_CODE_MAX_ATTEMPTS,
            })

        if current is None:
            assignment_status = "unassigned"
        elif stats["pending"] and stats["assigned_to_current"] < stats["pending"] + stats["in_progress"]:
            assignment_status = "partially_assigned"
        else:
            assignment_status = "assigned"

        def _admin_label(admin_id):
            a = admins.get(admin_id)
            return (a.full_name or a.email) if a else None

        return {
            "success": True,
            "subscription": subscription_admin_view(sub),
            "customer": {
                "user_id": user.user_id, "full_name": user.full_name, "phone": user.phone, "email": user.email,
            } if user else None,
            "provider": {
                "provider_id": kitchen.provider_id, "business_name": kitchen.business_name,
                "mobile_number": kitchen.mobile_number, "area": kitchen.area, "city": kitchen.city,
                "pincode": kitchen.pincode,
            } if kitchen else None,
            "plan": {
                "subscription_plan_id": plan.subscription_plan_id, "subscription_type": plan.subscription_type,
                "meal_slot": plan.meal_slot, "duration_days": plan.duration_days,
                "discount_percent": plan.discount_percent, "free_skips": plan.free_skips,
            } if plan else None,
            "delivery_address": address_view(address) if address else None,
            "packages": packages,
            "delivery_boy": _partner_brief(boys.get(current), sub.vendor_reference_id),
            "assignment_status": assignment_status,
            "can_assign": sub.status in delivery_assignment.ASSIGNABLE_SUBSCRIPTION_STATUSES,
            "stats": stats,
            "assignment_history": [
                {
                    "assignment_id": h.assignment_id,
                    "delivery_boy_id": h.delivery_boy_reference_id,
                    "delivery_boy_name": (
                        (boys[h.delivery_boy_reference_id].full_name or boys[h.delivery_boy_reference_id].mobile_number)
                        if h.delivery_boy_reference_id in boys else None
                    ),
                    "status": h.status,
                    "assigned_at": h.assigned_at,
                    "assigned_by_type": h.assigned_by_type,
                    "assigned_by_name": _admin_label(h.assigned_by),
                    "orders_assigned": h.orders_assigned,
                    "note": h.note,
                    "ended_at": h.ended_at,
                    "ended_by_name": _admin_label(h.ended_by),
                    "end_reason": h.end_reason,
                }
                for h in history
            ],
            "orders": order_rows,
        }

    # ── Subscription delivery assignment ──────────────────

    @staticmethod
    def assign_subscription_delivery_boy(db: Session, subscription_id: str, payload, admin_id: str, ip: str | None = None):
        sub = _locked_subscription(db, subscription_id)
        boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == payload.delivery_boy_id).with_for_update().first()
        if boy is None:
            raise DomainError("Delivery partner not found", 404)
        summary = delivery_assignment.assign(db, sub, boy, actor_id=admin_id, actor_type="admin", note=payload.note, ip=ip)
        db.commit()
        verb = {"assigned": "assigned", "reassigned": "reassigned", "unchanged": "already assigned"}[summary["action"]]
        message = f"Subscription {verb} to {boy.full_name or boy.mobile_number}: {summary['assigned_orders']} open meal(s)"
        if summary["skipped"]["in_progress"]:
            message += f"; {summary['skipped']['in_progress']} already picked up stay with their partner"
        if not boy.is_online:
            message += " (partner is currently offline)"
        return {"success": True, "message": message, **summary}

    @staticmethod
    def unassign_subscription_delivery_boy(db: Session, subscription_id: str, payload, admin_id: str, ip: str | None = None):
        sub = _locked_subscription(db, subscription_id)
        result = delivery_assignment.unassign(db, sub, actor_id=admin_id, actor_type="admin", note=payload.reason, ip=ip)
        db.commit()
        return {
            "success": True,
            "message": f"Delivery partner removed; {result['released_orders']} open meal(s) are now unassigned",
            **result,
        }

    # ── Verification lock reset ───────────────────────────

    @staticmethod
    def reset_verification(db: Session, kind: str, order_id: str, payload, admin_id: str, ip: str | None = None):
        order = _sub_order(db, order_id) if kind == "subscription" else _extra_order(db, order_id)
        if order.status in ("delivered", "cancelled", "skipped"):
            raise DomainError(f"This order is already {order.status}.")
        if not (payload.pickup or payload.delivery):
            raise DomainError("Choose the pickup and / or delivery attempts to reset")
        before = {"pickup_code_attempts": order.pickup_code_attempts, "delivery_code_attempts": order.delivery_code_attempts}
        if payload.pickup:
            order.pickup_code_attempts = 0
        if payload.delivery:
            order.delivery_code_attempts = 0
        oid = order.order_id if kind == "subscription" else order.extra_order_id
        record_audit(
            db, table="subscription.orders" if kind == "subscription" else "subscription.extra_orders",
            record_id=oid, old=before,
            new={
                "event": "verification_attempts_reset", "reason": payload.reason,
                "pickup_code_attempts": order.pickup_code_attempts,
                "delivery_code_attempts": order.delivery_code_attempts,
            },
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return {
            "success": True,
            "message": "Verification attempts reset; the partner can try the code again",
            "order_id": str(oid),
        }

    # ── Forced status (super admin) ───────────────────────

    @staticmethod
    def force_update_order_status(db: Session, order_id: str, payload, admin_id: str, ip: str | None = None):
        if payload.status not in SUB_ORDER_STATUSES:
            raise DomainError(f"Invalid status. Must be one of: {', '.join(SUB_ORDER_STATUSES)}")
        order = _sub_order(db, order_id)
        assert_sub_order_transition(order.status, payload.status, "admin")
        before = order_admin_view(order)

        refunded = None
        order.status = payload.status
        if payload.status == "delivered":
            order.delivered_at = order.delivered_at or now_utc()
            meals.settle_subscription_meal(db, order)
        elif payload.status == "cancelled":
            sub = db.query(Subscription).filter(
                Subscription.subscription_id == order.subscription_reference_id
            ).with_for_update().first()
            order.cancel_reason = f"admin: {payload.reason}"
            refunded = meals.refund_meal(
                db, order, sub, reason="order_cancel_refund",
                description=f"Refund for cancelled {order.meal_slot} on {order.order_date}",
            )
            notify.customer(
                db, order.user_reference_id, "order_cancelled", "Meal cancelled",
                f"Your {order.meal_slot} on {order.order_date} was cancelled by Orleeno support. "
                f"Rs {refunded} refunded to your wallet.",
                {"order_id": str(order.order_id)},
            )

        record_audit(
            db, table="subscription.orders", record_id=order.order_id,
            old=before, new={**order_admin_view(order), "reason": payload.reason},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        business_event("order.force_status", order_id=order_id, status=payload.status, admin_id=admin_id)
        return {
            "success": True,
            "message": f"Order status forced to '{payload.status}'",
            "order_id": order_id,
            "refund_amount": refunded,
        }

    @staticmethod
    def force_update_extra_order_status(db: Session, order_id: str, payload, admin_id: str, ip: str | None = None):
        if payload.status not in EXTRA_ORDER_STATUSES:
            raise DomainError(f"Invalid status. Must be one of: {', '.join(EXTRA_ORDER_STATUSES)}")
        order = _extra_order(db, order_id)
        assert_extra_order_transition(order.status, payload.status, "admin")
        before = extra_order_admin_view(order)

        refunded = None
        order.status = payload.status
        if payload.status == "delivered":
            order.delivered_at = order.delivered_at or now_utc()
            meals.settle_extra_order(db, order)
        elif payload.status == "cancelled":
            order.cancel_reason = f"admin: {payload.reason}"
            refunded = meals.refund_extra_order(
                db, order, reason="order_cancel_refund",
                description=f"Refund for cancelled one-time order on {order.delivery_date}",
            )
            notify.customer(
                db, order.user_reference_id, "order_cancelled", "Order cancelled",
                f"Your one-time order for {order.delivery_date} was cancelled by Orleeno support. "
                f"Rs {refunded} refunded to your wallet.",
                {"extra_order_id": str(order.extra_order_id)},
            )

        record_audit(
            db, table="subscription.extra_orders", record_id=order.extra_order_id,
            old=before, new={**extra_order_admin_view(order), "reason": payload.reason},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        business_event("extra_order.force_status", order_id=order_id, status=payload.status, admin_id=admin_id)
        return {
            "success": True,
            "message": f"Extra order status forced to '{payload.status}'",
            "order_id": order_id,
            "refund_amount": refunded,
        }

    # ── Delivery partner assignment ───────────────────────

    @staticmethod
    def _assign(db: Session, order, *, kind: str, on: date, delivery_boy_id, admin_id: str, ip: str | None, reason: str | None):
        allowed = SUB_ASSIGNABLE if kind == "subscription" else EXTRA_ASSIGNABLE
        if order.status not in allowed:
            raise DomainError(f"Cannot assign a delivery partner to an order that is '{order.status}'.")
        if on < today_local():
            raise DomainError("This order's date has passed.")
        boy = _partner(db, delivery_boy_id)
        partner_leave.assert_available(db, boy.delivery_boy_id, on)

        previous_id = order.delivery_boy_reference_id
        order.delivery_boy_reference_id = boy.delivery_boy_id
        if kind != "subscription":
            # one checkout is one trip: its other open lines go with the same partner
            for line in checkout.siblings(db, order, statuses=EXTRA_ASSIGNABLE):
                line.delivery_boy_reference_id = boy.delivery_boy_id
        order_key = "order_id" if kind == "subscription" else "extra_order_id"
        oid = getattr(order, order_key)

        notify.delivery_partner(
            db, boy.delivery_boy_id, "order_assigned", "New delivery assigned",
            f"{order.meal_slot.title()} delivery on {on}.",
            {"order_id": str(oid), "kind": kind},
        )
        notify.kitchen(
            db, order.vendor_reference_id, "partner_assigned",
            "Delivery partner changed" if previous_id else "Delivery partner assigned",
            f"{boy.full_name or 'A delivery partner'} will collect the {order.meal_slot} order on {on}.",
            {"order_id": str(oid), "kind": kind},
        )
        if previous_id and str(previous_id) != str(boy.delivery_boy_id):
            notify.delivery_partner(
                db, previous_id, "order_unassigned", "Delivery reassigned",
                f"The {order.meal_slot} delivery on {on} was moved to another partner.",
                {"order_id": str(oid), "kind": kind},
            )
        record_audit(
            db, table="subscription.orders" if kind == "subscription" else "subscription.extra_orders",
            record_id=oid, old={"delivery_boy_id": previous_id},
            new={"delivery_boy_id": boy.delivery_boy_id, "reason": reason},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return {
            "success": True,
            "message": f"Delivery partner {'reassigned' if previous_id else 'assigned'} successfully"
            + ("" if boy.is_online else " (partner is currently offline)"),
            "order_id": str(oid),
            "delivery_boy_id": str(boy.delivery_boy_id),
            "previous_delivery_boy_id": str(previous_id) if previous_id else None,
        }

    @staticmethod
    def assign_delivery_boy(db: Session, order_id: str, payload, admin_id: str, ip: str | None = None):
        order = _sub_order(db, order_id)
        return AdminOrderService._assign(
            db, order, kind="subscription", on=order.order_date, delivery_boy_id=payload.delivery_boy_id,
            admin_id=admin_id, ip=ip, reason=payload.reason,
        )

    @staticmethod
    def assign_extra_delivery_boy(db: Session, order_id: str, payload, admin_id: str, ip: str | None = None):
        order = _extra_order(db, order_id)
        return AdminOrderService._assign(
            db, order, kind="extra", on=order.delivery_date, delivery_boy_id=payload.delivery_boy_id,
            admin_id=admin_id, ip=ip, reason=payload.reason,
        )

    # ── Kitchen reassignment (holiday cover) ──────────────

    @staticmethod
    def reassign_provider(db: Session, order_id: str, payload, admin_id: str, ip: str | None = None):
        order = _sub_order(db, order_id)
        if order.status != "scheduled":
            raise DomainError(f"Only scheduled meals can be moved (this one is '{order.status}').")
        if not is_on_holiday(db, order.vendor_reference_id, order.order_date):
            raise DomainError("Mark the current kitchen unavailable for this date before moving its meals.")

        new_provider_id = str(payload.new_provider_id)
        provider = _new_kitchen(
            db, new_provider_id, order.vendor_reference_id, order.order_date, order.meal_slot,
            order.delivery_address_reference_id,
        )
        capacity.assert_kitchen_room(
            db, provider_id=provider.provider_id, slots=[order.meal_slot],
            start=order.order_date, end=order.order_date, quantity=1,
        )

        previous_provider_id = str(order.vendor_reference_id)
        order.vendor_reference_id = provider.provider_id
        # pickup now needs the new kitchen's daily code; the new kitchen (or an admin) picks the partner
        order.delivery_boy_reference_id = None
        order.pickup_code_attempts = 0

        record_audit(
            db, table="subscription.orders", record_id=order.order_id,
            old={"vendor_id": previous_provider_id}, new={"vendor_id": new_provider_id, "reason": payload.reason},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        notify.customer(
            db, order.user_reference_id, "order_update", "Your meal is coming from another kitchen",
            f"Your usual kitchen is closed on {order.order_date}; your {order.meal_slot} will be prepared by "
            f"{provider.business_name}.",
            {"order_id": str(order.order_id)},
        )
        db.commit()
        return {
            "success": True,
            "message": "Order reassigned to new provider successfully",
            "order_id": order_id,
            "previous_provider_id": previous_provider_id,
            "new_provider_id": new_provider_id,
            "order_date": str(order.order_date),
            "meal_slot": order.meal_slot,
        }

    @staticmethod
    def reassign_extra_order_provider(db: Session, order_id: str, payload, admin_id: str, ip: str | None = None):
        order = _extra_order(db, order_id)
        if order.status not in ("pending", "confirmed"):
            raise DomainError(f"Only pending or confirmed orders can be moved (this one is '{order.status}').")
        if not is_on_holiday(db, order.vendor_reference_id, order.delivery_date):
            raise DomainError("Mark the current kitchen unavailable for this date before moving its orders.")

        new_provider_id = str(payload.new_provider_id)
        provider = _new_kitchen(
            db, new_provider_id, order.vendor_reference_id, order.delivery_date, order.meal_slot,
            order.address_reference_id,
        )
        # the whole checkout moves: it is one delivery
        moving = [order, *checkout.siblings(db, order, statuses=("pending", "confirmed"))]
        capacity.assert_kitchen_room(
            db, provider_id=provider.provider_id, slots=[order.meal_slot],
            start=order.delivery_date, end=order.delivery_date, quantity=sum(o.quantity for o in moving),
        )

        previous_provider_id = str(order.vendor_reference_id)
        for line in moving:
            line.vendor_reference_id = provider.provider_id
            line.delivery_boy_reference_id = None
            line.pickup_code_attempts = 0
            # the new kitchen confirms it again
            line.status = "pending"

        record_audit(
            db, table="subscription.extra_orders", record_id=order.extra_order_id,
            old={"vendor_id": previous_provider_id}, new={"vendor_id": new_provider_id, "reason": payload.reason},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        notify.customer(
            db, order.user_reference_id, "order_update", "Your order is coming from another kitchen",
            f"Your one-time order for {order.delivery_date} will be prepared by {provider.business_name}.",
            {"extra_order_id": str(order.extra_order_id)},
        )
        db.commit()
        return {
            "success": True,
            "message": "Extra order reassigned to new provider successfully",
            "order_id": order_id,
            "previous_provider_id": previous_provider_id,
            "new_provider_id": new_provider_id,
            "delivery_date": str(order.delivery_date),
            "meal_slot": order.meal_slot,
        }
