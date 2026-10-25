"""
Kitchen view of orders.

The kitchen never sees the customer's delivery code: that code proves the
customer received the food and must only travel customer -> delivery
partner. The kitchen has one pickup code per day instead (GET
/provider/pickup-code), which it reads out to the partner at hand-over.

Kitchens may only: start preparing a meal and mark it ready for pickup;
confirm, start preparing, mark ready or reject (refunded) a one-time order;
assign a delivery partner to an order that has none. Changing an existing
assignment is Orleeno's job (admin). Pickup and delivery are recorded by the
delivery partner, and a partner can pick up ONLY after the kitchen marked
the order Ready for Pickup (see _mark_ready).
"""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.core.audit import business_event
from app.core.clock import local_datetime, now_local, today_local
from app.core.config import PICKUP_CODE_MAX_ATTEMPTS
from app.core.errors import DomainError
from app.domain import checkout, delivery_assignment, holidays, item_quantity, notify, orders as meals, partner_leave
from app.domain.meal_views import MealContext
from app.domain.slots import SLOTS, SLOT_WINDOWS, delivery_window, expand_plan_slot
from app.domain.status import (
    assert_sub_order_transition, assert_extra_order_transition, allowed_next,
    SUB_UNPICKED_STATUSES, EXTRA_UNPICKED_STATUSES, IN_HAND_STATUSES, KITCHEN_READY_FROM,
)
from app.domain.vendor_partner import kitchen_address
from app.models.provider_model import Provider
from app.domain.verification import (
    NO_PICKUP_CODE_MESSAGE, pickup_code_row, pickup_code_value, regenerate_pickup_code,
)
from app.models.delivery_boy_model import DeliveryBoy
from app.models.extra_order_model import ExtraOrder
from app.models.menu_package_item_model import MenuPackageItem
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.user_address_model import UserAddress
from app.models.user_model import User

MAX_LIST = 500
NEXT_BATCH_DAYS = 7

# still at the kitchen: part of a delivery batch
BATCH_SUB_STATUSES = ("scheduled", "preparing", "ready_for_pickup")
BATCH_EXTRA_STATUSES = ("pending", "confirmed", "preparing", "ready_for_pickup")
_HOLIDAY_REASONS = ("vendor_holiday", "vendor_emergency_holiday", "vendor_holiday_not_owed", "kitchen_holiday")


def _first_name(user: User | None) -> str | None:
    if user is None or not user.full_name:
        return None
    return user.full_name.split()[0]


def _kitchen_actions(kind: str, status: str) -> list[str]:
    """
    What the kitchen can do now. Preparing and ready for pickup are allowed at
    any time, also before the delivery date; the partner still collects the
    meal on its delivery date with that day's pickup code.
    """
    return allowed_next(kind, status, "provider")


def _sub_order_view(o: Order, packages, user, address, boy, ctx: MealContext | None = None) -> dict:
    if ctx is not None:
        packages = ctx.packages(o)
    return {
        "order_id": o.order_id,
        "subscription_reference_id": o.subscription_reference_id,
        "user_reference_id": o.user_reference_id,
        "vendor_reference_id": o.vendor_reference_id,
        "delivery_address_reference_id": o.delivery_address_reference_id,
        "order_date": o.order_date,
        "meal_slot": o.meal_slot,
        "status": o.status,
        "is_free_skip": o.is_free_skip,
        "delivered_at": o.delivered_at,
        "delivery_notes": o.delivery_notes,
        "cancel_reason": o.cancel_reason,
        "picked_up_at": o.picked_up_at,
        "pickup_locked": (o.pickup_code_attempts or 0) >= PICKUP_CODE_MAX_ATTEMPTS,
        "delivery_boy_reference_id": o.delivery_boy_reference_id,
        "delivery_boy_name": boy.full_name if boy else None,
        "customer_name": _first_name(user),
        "delivery_area": f"{address.city} {address.pin_code}" if address else None,
        "packages": packages,
        "next_actions": _kitchen_actions("subscription", o.status),
        # skipped / cancelled / holiday meals are not cooked
        "on_prep_list": o.status not in ("skipped", "cancelled"),
        "change_tags": ctx.tags(o) if ctx else [],
        "holiday_outcome": ctx.holiday_outcome(o) if ctx else None,
        "original_vendor_name": ctx.kitchen_name(o.original_vendor_reference_id)
        if ctx and o.original_vendor_reference_id else None,
        "created_at": o.created_at,
    }


def _extra_order_view(o: ExtraOrder, package, user, address, boy) -> dict:
    return {
        "extra_order_id": o.extra_order_id,
        "user_reference_id": o.user_reference_id,
        "vendor_reference_id": o.vendor_reference_id,
        "address_reference_id": o.address_reference_id,
        "package_reference_id": o.package_reference_id,
        "package_name": package.package_name if package else None,
        "quantity": o.quantity,
        # What the kitchen earns per unit (its selling price), not what the customer paid
        "unit_price": o.unit_price,
        "total_price": o.unit_price * o.quantity,
        "delivery_date": o.delivery_date,
        "meal_slot": o.meal_slot,
        "status": o.status,
        "cancel_reason": o.cancel_reason,
        "picked_up_at": o.picked_up_at,
        "pickup_locked": (o.pickup_code_attempts or 0) >= PICKUP_CODE_MAX_ATTEMPTS,
        "delivery_boy_reference_id": o.delivery_boy_reference_id,
        "delivery_boy_name": boy.full_name if boy else None,
        "customer_name": _first_name(user),
        "delivery_area": f"{address.city} {address.pin_code}" if address else None,
        "next_actions": _kitchen_actions("extra", o.status),
        "created_at": o.created_at,
    }


def _pickup_pending_without_partner(db: Session, order, kind: str) -> None:
    """A packed order nobody is coming for: tell the kitchen so it assigns someone."""
    if order.delivery_boy_reference_id is not None:
        return
    ref = order.order_id if kind == "subscription" else order.extra_order_id
    notify.kitchen(
        db, order.vendor_reference_id, "pickup_pending", "Pickup pending - no delivery partner",
        f"The {order.meal_slot} order is ready but no delivery partner is assigned. Assign one from the order, "
        "or contact Orleeno support.",
        {"order_id": str(ref), "kind": kind},
    )


def _lookup(db: Session, model, key_col, ids):
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {getattr(r, key_col): r for r in db.query(model).filter(getattr(model, key_col).in_(ids)).all()}


def _subscription_views(db: Session, subs) -> list[dict]:
    """Subscriptions with the customer's first name, area, packages and assigned partner."""
    users = _lookup(db, User, "user_id", (s.user_reference_id for s in subs))
    addresses = _lookup(db, UserAddress, "user_address_id", (s.user_address_reference_id for s in subs))
    boys = _lookup(db, DeliveryBoy, "delivery_boy_id", (s.delivery_boy_reference_id for s in subs))
    pkgs = defaultdict(list)
    sub_ids = [s.subscription_id for s in subs]
    if sub_ids:
        rows = (
            db.query(SubscriptionPackage, MenuPackage)
            .join(MenuPackage, MenuPackage.package_id == SubscriptionPackage.package_reference_id)
            .filter(SubscriptionPackage.subscription_reference_id.in_(sub_ids))
            .all()
        )
        for sp, mp in rows:
            pkgs[sp.subscription_reference_id].append(
                {"package_id": mp.package_id, "package_name": mp.package_name, "quantity": sp.quantity}
            )
    out = []
    for s in subs:
        address = addresses.get(s.user_address_reference_id)
        boy = boys.get(s.delivery_boy_reference_id)
        view = {a.key: getattr(s, a.key) for a in sa_inspect(Subscription).column_attrs}
        snapshot = s.pricing_snapshot or {}
        view.pop("pricing_snapshot", None)  # Orleeno's margins and partner payout are not the kitchen's business
        view.update({
            "customer_name": _first_name(users.get(s.user_reference_id)),
            "delivery_area": f"{address.city} {address.pin_code}" if address else None,
            "delivery_boy_name": boy.full_name if boy else None,
            "packages": pkgs.get(s.subscription_id, []),
            "meal_slots": expand_plan_slot(s.meal_slot),
            # the plan discount is taken once off the subscription total and funded by Orleeno;
            # the kitchen earns its per-meal price for every delivered meal
            "discount_percent": snapshot.get("discount_percent"),
            "meals_total": snapshot.get("deliveries"),
            "kitchen_earning_per_meal": (snapshot.get("settlement") or {}).get("provider_earning_per_delivery"),
        })
        out.append(view)
    return out


_NOT_READY_REASONS = {
    "skipped": "The customer skipped this meal; it cannot be marked ready for pickup.",
    "cancelled": "This order is cancelled; it cannot be marked ready for pickup.",
    "delivered": "This order is already delivered.",
    "delivery_failed": "This order's delivery has already been attempted.",
    "picked_up": "The delivery partner has already picked this order up.",
    "out_for_delivery": "The delivery partner has already picked this order up.",
    "pending": "Confirm the order first, then mark it ready for pickup.",
}


def _collect_text(day: date | None, plural: bool = False) -> str:
    it = "them" if plural else "it"
    if day is None or day == today_local():
        return f"Collect {it} with today's pickup code."
    return f"Collect {it} on {day:%d %b} with that day's pickup code."


def _mark_ready(db: Session, vendor_id, order, kind: str, notify_people: bool = True) -> dict:
    """
    The kitchen confirms the food is packed: the only way an order becomes
    collectable. Runs on the row-locked order; marking an order that is
    already ready again changes nothing and notifies nobody, so repeated taps
    and retried requests are safe. A one-time checkout is one trip, so its
    other lines still at the kitchen are marked ready with it.
    """
    is_sub = kind == "subscription"
    day = order.order_date if is_sub else order.delivery_date
    ref = order.order_id if is_sub else order.extra_order_id
    if order.status == "ready_for_pickup":
        return {"already": True, "lines": [order]}
    if order.status not in KITCHEN_READY_FROM:
        raise DomainError(
            _NOT_READY_REASONS.get(order.status, f"An order that is {order.status} cannot be marked ready."),
            409, code="NOT_ELIGIBLE_FOR_PICKUP",
        )
    # any time, also before the delivery date: the partner collects it on that date
    (assert_sub_order_transition if is_sub else assert_extra_order_transition)(order.status, "ready_for_pickup", "provider")

    lines = [order]
    if not is_sub:
        lines += [
            line for line in checkout.siblings(db, order, statuses=KITCHEN_READY_FROM)
            if str(line.vendor_reference_id) == str(vendor_id)
        ]
    for line in lines:
        line.status = "ready_for_pickup"
    if not notify_people:
        return {"already": False, "lines": lines}

    # what the partner needs at the kitchen door
    kitchen = db.query(Provider).filter(Provider.provider_id == vendor_id).first()
    if is_sub:
        names = [p["package_name"] for p in MealContext(db, [order]).packages(order) if p["package_name"]]
    else:
        names = [
            name for (name,) in db.query(MenuPackage.package_name)
            .filter(MenuPackage.package_id.in_([line.package_reference_id for line in lines]))
        ]
    where = kitchen_address(kitchen) or "the kitchen"
    kitchen_name = (kitchen.business_name if kitchen else None) or "The kitchen"
    reference = (
        f"subscription #{str(order.subscription_reference_id)[:8].upper()}" if is_sub
        else f"order #{str(order.checkout_id or ref)[:8].upper()}"
    )
    notify.delivery_partner(
        db, order.delivery_boy_reference_id, "order_ready", "Ready for pickup",
        f"{', '.join(names) or 'The order'} ({order.meal_slot}, {reference}) is packed at {kitchen_name}, {where}. "
        f"{_collect_text(day)}",
        {
            "order_id": str(ref), "kind": "subscription" if is_sub else "extra",
            "subscription_id": str(order.subscription_reference_id) if is_sub else None,
            "provider_id": str(vendor_id), "package_names": names, "meal_slot": order.meal_slot,
            "pickup_address": where, "kitchen_name": kitchen_name,
        },
    )
    _pickup_pending_without_partner(db, order, kind)
    business_event("order.ready_for_pickup", order_id=ref, kind=kind, lines=len(lines),
                   delivery_boy_id=order.delivery_boy_reference_id)
    return {"already": False, "lines": lines}


class ProviderOrderService:

    # ── Subscriptions ─────────────────────────────────────

    @staticmethod
    def list_subscriptions(db: Session, vendor_id: str, status: str = None):
        q = db.query(Subscription).filter(Subscription.vendor_reference_id == vendor_id)
        if status:
            q = q.filter(Subscription.status == status)
        subs = q.order_by(Subscription.created_at.desc()).limit(MAX_LIST).all()
        return {"success": True, "total": len(subs), "subscriptions": _subscription_views(db, subs)}

    @staticmethod
    def get_subscription_detail(db: Session, vendor_id: str, subscription_id: str):
        sub = db.query(Subscription).filter(
            Subscription.subscription_id == subscription_id,
            Subscription.vendor_reference_id == vendor_id,
        ).first()
        if not sub:
            raise DomainError("Subscription not found", 404)
        orders = (
            db.query(Order)
            .filter(Order.subscription_reference_id == sub.subscription_id, Order.vendor_reference_id == vendor_id)
            .order_by(Order.order_date.asc(), Order.meal_slot.asc())
            .all()
        )
        view = _subscription_views(db, [sub])[0]
        users = _lookup(db, User, "user_id", [sub.user_reference_id])
        addresses = _lookup(db, UserAddress, "user_address_id", (o.delivery_address_reference_id for o in orders))
        boys = _lookup(db, DeliveryBoy, "delivery_boy_id", (o.delivery_boy_reference_id for o in orders))
        ctx = MealContext(db, orders)
        return {
            "success": True,
            "subscription": view,
            "orders": [
                _sub_order_view(
                    o, view["packages"], users.get(o.user_reference_id),
                    addresses.get(o.delivery_address_reference_id), boys.get(o.delivery_boy_reference_id), ctx,
                )
                for o in orders
            ],
        }

    # ── Subscription meals ────────────────────────────────

    @staticmethod
    def list_subscription_orders(
        db: Session,
        vendor_id: str,
        order_date: date = None,
        status: str = None,
        from_date: date = None,
        to_date: date = None,
        meal_slot: str = None,
        page: int = 1,
        limit: int = MAX_LIST,
    ):
        q = db.query(Order).filter(Order.vendor_reference_id == vendor_id)
        if order_date is None and from_date is None and to_date is None:
            order_date = today_local()
        if order_date:
            q = q.filter(Order.order_date == order_date)
        if from_date:
            q = q.filter(Order.order_date >= from_date)
        if to_date:
            q = q.filter(Order.order_date <= to_date)
        if status:
            q = q.filter(Order.status == status)
        if meal_slot:
            q = q.filter(Order.meal_slot == meal_slot)
        total = q.count()
        orders = (
            q.order_by(Order.order_date.asc(), Order.meal_slot.asc(), Order.order_id)
            .offset((page - 1) * limit).limit(limit).all()
        )

        sub_ids = {o.subscription_reference_id for o in orders}
        pkgs = defaultdict(list)
        if sub_ids:
            rows = (
                db.query(SubscriptionPackage, MenuPackage)
                .join(MenuPackage, MenuPackage.package_id == SubscriptionPackage.package_reference_id)
                .filter(SubscriptionPackage.subscription_reference_id.in_(sub_ids))
                .all()
            )
            for sp, mp in rows:
                pkgs[sp.subscription_reference_id].append(
                    {"package_id": mp.package_id, "package_name": mp.package_name, "quantity": sp.quantity}
                )
        users = _lookup(db, User, "user_id", (o.user_reference_id for o in orders))
        addresses = _lookup(db, UserAddress, "user_address_id", (o.delivery_address_reference_id for o in orders))
        boys = _lookup(db, DeliveryBoy, "delivery_boy_id", (o.delivery_boy_reference_id for o in orders))
        ctx = MealContext(db, orders)

        return {
            "success": True,
            "date": order_date,
            "total": total,
            "page": page,
            "has_more": (page - 1) * limit + len(orders) < total,
            "orders": [
                _sub_order_view(
                    o,
                    pkgs.get(o.subscription_reference_id, []),
                    users.get(o.user_reference_id),
                    addresses.get(o.delivery_address_reference_id),
                    boys.get(o.delivery_boy_reference_id),
                    ctx,
                )
                for o in orders
            ],
        }

    @staticmethod
    def update_subscription_order_status(db: Session, vendor_id: str, order_id: str, new_status: str):
        order = (
            db.query(Order)
            .filter(Order.order_id == order_id, Order.vendor_reference_id == vendor_id)
            .with_for_update()
            .first()
        )
        if not order:
            raise DomainError("Order not found", 404)

        if new_status == "ready_for_pickup":
            result = _mark_ready(db, vendor_id, order, "subscription")
            db.commit()
            return {
                "success": True,
                "message": "Already marked ready for pickup" if result["already"]
                else "Marked ready for pickup; the delivery partner can collect it now",
                "order_id": str(order.order_id),
                "status": order.status,
                "already_done": result["already"],
            }

        assert_sub_order_transition(order.status, new_status, "provider")

        order.status = new_status
        if new_status == "preparing":
            notify.customer(
                db, order.user_reference_id, "order_status", "Your meal is being prepared",
                f"Your {order.meal_slot} for {order.order_date} is being prepared.",
                {"order_id": str(order.order_id), "kind": "subscription"},
            )
        db.commit()
        return {
            "success": True,
            "message": f"Order status updated to '{new_status}'",
            "order_id": str(order.order_id),
            "status": order.status,
        }

    # ── One-time orders ───────────────────────────────────

    @staticmethod
    def list_extra_orders(
        db: Session,
        vendor_id: str,
        delivery_date: date = None,
        status: str = None,
        from_date: date = None,
        to_date: date = None,
    ):
        q = db.query(ExtraOrder).filter(ExtraOrder.vendor_reference_id == vendor_id)
        if delivery_date is None and from_date is None and to_date is None:
            from_date = today_local()
        if delivery_date:
            q = q.filter(ExtraOrder.delivery_date == delivery_date)
        if from_date:
            q = q.filter(ExtraOrder.delivery_date >= from_date)
        if to_date:
            q = q.filter(ExtraOrder.delivery_date <= to_date)
        if status:
            q = q.filter(ExtraOrder.status == status)
        orders = q.order_by(ExtraOrder.delivery_date.asc(), ExtraOrder.created_at.desc()).limit(MAX_LIST).all()

        packages = _lookup(db, MenuPackage, "package_id", (o.package_reference_id for o in orders))
        users = _lookup(db, User, "user_id", (o.user_reference_id for o in orders))
        addresses = _lookup(db, UserAddress, "user_address_id", (o.address_reference_id for o in orders))
        boys = _lookup(db, DeliveryBoy, "delivery_boy_id", (o.delivery_boy_reference_id for o in orders))
        return {
            "success": True,
            "total": len(orders),
            "orders": [
                _extra_order_view(
                    o,
                    packages.get(o.package_reference_id),
                    users.get(o.user_reference_id),
                    addresses.get(o.address_reference_id),
                    boys.get(o.delivery_boy_reference_id),
                )
                for o in orders
            ],
        }

    @staticmethod
    def update_extra_order_status(db: Session, vendor_id: str, order_id: str, new_status: str):
        order = (
            db.query(ExtraOrder)
            .filter(ExtraOrder.extra_order_id == order_id, ExtraOrder.vendor_reference_id == vendor_id)
            .with_for_update()
            .first()
        )
        if not order:
            raise DomainError("Extra order not found", 404)

        if new_status == "ready_for_pickup":
            result = _mark_ready(db, vendor_id, order, "extra")
            db.commit()
            return {
                "success": True,
                "message": "Already marked ready for pickup" if result["already"]
                else "Marked ready for pickup; the delivery partner can collect it now",
                "order_id": str(order.extra_order_id),
                "status": order.status,
                "already_done": result["already"],
                "also_updated": [str(line.extra_order_id) for line in result["lines"][1:]],
            }

        assert_extra_order_transition(order.status, new_status, "provider")

        order.status = new_status
        if new_status == "cancelled":
            order.cancel_reason = "rejected_by_kitchen"
            refund = meals.refund_extra_order(
                db, order, reason="order_rejected_refund", description="Refund - order declined by the kitchen"
            )
            notify.customer(
                db, order.user_reference_id, "order_status", "Order declined",
                f"The kitchen could not take your {order.meal_slot} order for {order.delivery_date}. Rs {refund} refunded.",
                {"order_id": str(order.extra_order_id), "kind": "extra"},
            )
            business_event("extra_order.rejected", order_id=order.extra_order_id, refund=refund)
        elif new_status in ("confirmed", "preparing"):
            notify.customer(
                db, order.user_reference_id, "order_status",
                "Order confirmed" if new_status == "confirmed" else "Your order is being prepared",
                f"Your {order.meal_slot} order for {order.delivery_date} is {new_status}.",
                {"order_id": str(order.extra_order_id), "kind": "extra"},
            )
        db.commit()
        return {
            "success": True,
            "message": f"Extra order status updated to '{new_status}'",
            "order_id": str(order.extra_order_id),
            "status": order.status,
        }

    # ── Delivery partner assignment ───────────────────────

    @staticmethod
    def _assignable_partner(db: Session, vendor_id: str, delivery_boy_id) -> DeliveryBoy:
        boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == delivery_boy_id).first()
        if delivery_assignment.partner_block_reason(db, boy, vendor_id):
            raise DomainError("This delivery partner cannot be assigned to your kitchen", 404)
        if not boy.is_online:
            raise DomainError(f"{boy.full_name or 'This partner'} is offline right now")
        return boy

    @staticmethod
    def assign_delivery_boy(db: Session, vendor_id: str, kind: str, order_id, delivery_boy_id):
        if kind == "subscription":
            order = db.query(Order).filter(Order.order_id == order_id, Order.vendor_reference_id == vendor_id).with_for_update().first()
            on = order.order_date if order else None
            open_statuses = SUB_UNPICKED_STATUSES
        else:
            order = db.query(ExtraOrder).filter(ExtraOrder.extra_order_id == order_id, ExtraOrder.vendor_reference_id == vendor_id).with_for_update().first()
            on = order.delivery_date if order else None
            open_statuses = EXTRA_UNPICKED_STATUSES
        if not order:
            raise DomainError("Order not found", 404)
        if order.status not in open_statuses:
            raise DomainError(f"A delivery partner cannot be assigned to an order that is {order.status.replace('_', ' ')}")
        if order.delivery_boy_reference_id is not None:
            # kitchens fill gaps; changing who delivers is done by Orleeno
            raise DomainError(
                "A delivery partner is already assigned. Contact Orleeno support to change it.",
                409,
                code="PARTNER_ALREADY_ASSIGNED",
            )
        if on < today_local() or on > today_local() + timedelta(days=1):
            raise DomainError("Delivery partners can be assigned for today's and tomorrow's orders only")

        boy = ProviderOrderService._assignable_partner(db, vendor_id, delivery_boy_id)
        partner_leave.assert_available(db, boy.delivery_boy_id, on)
        order.delivery_boy_reference_id = boy.delivery_boy_id
        if kind != "subscription":
            # the rest of the same checkout travels with it
            for line in checkout.siblings(db, order, statuses=open_statuses):
                if line.delivery_boy_reference_id is None:
                    line.delivery_boy_reference_id = boy.delivery_boy_id
        ref = str(order.order_id if kind == "subscription" else order.extra_order_id)
        notify.delivery_partner(
            db, boy.delivery_boy_id, "order_assigned", "New delivery assigned",
            f"{'Subscription' if kind == 'subscription' else 'One-time'} {order.meal_slot} delivery for {on} has been assigned to you.",
            {"order_id": ref, "kind": "subscription" if kind == "subscription" else "extra"},
        )
        db.commit()
        return {
            "success": True,
            "message": "Delivery partner assigned",
            "order_id": ref,
            "delivery_boy_id": str(boy.delivery_boy_id),
            "delivery_boy_name": boy.full_name,
        }

    # ── Daily pickup code ─────────────────────────────────

    @staticmethod
    def _pickup_code_view(db: Session, vendor_id: str, row) -> dict:
        day = row.code_date
        awaiting = (
            db.query(Order).filter(
                Order.vendor_reference_id == vendor_id, Order.order_date == day,
                Order.status.in_(SUB_UNPICKED_STATUSES),
            ).count()
            + db.query(ExtraOrder).filter(
                ExtraOrder.vendor_reference_id == vendor_id, ExtraOrder.delivery_date == day,
                ExtraOrder.status.in_(("confirmed", "preparing", "ready_for_pickup")),
            ).count()
        )
        handed_over = (
            db.query(Order).filter(
                Order.vendor_reference_id == vendor_id, Order.order_date == day,
                Order.status.in_(IN_HAND_STATUSES + ("delivered",)),
            ).count()
            + db.query(ExtraOrder).filter(
                ExtraOrder.vendor_reference_id == vendor_id, ExtraOrder.delivery_date == day,
                ExtraOrder.status.in_(IN_HAND_STATUSES + ("delivered",)),
            ).count()
        )
        return {
            "success": True,
            "code_date": day,
            "pickup_code": pickup_code_value(row),
            "expires_at": row.expires_at,
            "version": row.version,
            "regenerated_at": row.regenerated_at,
            "orders_awaiting_pickup": awaiting,
            "orders_picked_up": handed_over,
        }

    @staticmethod
    def get_pickup_code(db: Session, vendor_id: str):
        row = pickup_code_row(db, vendor_id, today_local())
        if row is None:
            # nothing to hand over today, so no code is generated or stored
            raise DomainError(NO_PICKUP_CODE_MESSAGE, 404, code="NO_PICKUP_CODE")
        view = ProviderOrderService._pickup_code_view(db, vendor_id, row)
        db.commit()
        return view

    @staticmethod
    def regenerate_pickup_code(db: Session, vendor_id: str, ip: str | None = None):
        row = regenerate_pickup_code(db, vendor_id, today_local(), actor_id=vendor_id, actor_type="provider", ip=ip)
        view = ProviderOrderService._pickup_code_view(db, vendor_id, row)
        db.commit()
        business_event("pickup_code.regenerated", provider_id=vendor_id, version=row.version)
        return {**view, "message": "New pickup code created. The previous code no longer works."}

    # ── Daily food calculator ─────────────────────────────

    @staticmethod
    def get_daily_food_summary(db: Session, vendor_id: str, summary_date: date, meal_slot: str = None):
        """
        How many of each package and item to cook. Skipped, cancelled and
        holiday meals are left out; a meal moved here from a closed kitchen
        counts the package this kitchen cooks for it. Items are counted per
        serving (no units).
        """
        sub_q = db.query(Order).filter(
            Order.vendor_reference_id == vendor_id,
            Order.order_date == summary_date,
            Order.status.notin_(["cancelled", "skipped"]),
        )
        if meal_slot:
            sub_q = sub_q.filter(Order.meal_slot == meal_slot)
        sub_orders = sub_q.all()

        extra_q = db.query(ExtraOrder).filter(
            ExtraOrder.vendor_reference_id == vendor_id,
            ExtraOrder.delivery_date == summary_date,
            ExtraOrder.status != "cancelled",
        )
        if meal_slot:
            extra_q = extra_q.filter(ExtraOrder.meal_slot == meal_slot)
        extra_orders = extra_q.all()

        meal_counts: dict = defaultdict(int)
        ctx = MealContext(db, sub_orders)
        for order in sub_orders:
            for pkg in ctx.packages(order):
                meal_counts[pkg["package_id"]] += pkg["quantity"]
        for eo in extra_orders:
            meal_counts[eo.package_reference_id] += eo.quantity

        tally: dict = defaultdict(int)
        pieces: dict = {}  # item -> total count to cook (only items with a count)
        if meal_counts:
            items = db.query(MenuPackageItem).filter(MenuPackageItem.package_reference_id.in_(list(meal_counts))).all()
            for item in items:
                name = item.item_name.strip()
                meals_of_item = meal_counts[item.package_reference_id]
                tally[name] += meals_of_item
                per_meal = item_quantity.count(item)
                if per_meal is not None:
                    pieces[name] = pieces.get(name, 0) + per_meal * meals_of_item

        packages = _lookup(db, MenuPackage, "package_id", meal_counts.keys())
        return {
            "success": True,
            "date": summary_date,
            "meal_slot": meal_slot or "all",
            "subscription_orders_count": len(sub_orders),
            "extra_orders_count": len(extra_orders),
            "total_orders_count": len(sub_orders) + len(extra_orders),
            "packages": [
                {"package_id": pid, "package_name": packages[pid].package_name if pid in packages else None, "meals": n}
                for pid, n in meal_counts.items()
            ],
            "items": [
                {"item_name": name, "total_servings": total, "total_quantity": pieces.get(name)}
                for name, total in sorted(tally.items())
            ],
        }

    # ── Next delivery batch and bulk ready (kitchen Home) ──

    @staticmethod
    def _batch_rows(db: Session, vendor_id, day: date, slot: str | None, *, lock: bool = False):
        """Meals of one batch (or of the whole day when slot is None) still at the kitchen."""
        subs = db.query(Order).filter(
            Order.vendor_reference_id == vendor_id,
            Order.order_date == day,
            Order.status.in_(BATCH_SUB_STATUSES),
        )
        extras = db.query(ExtraOrder).filter(
            ExtraOrder.vendor_reference_id == vendor_id,
            ExtraOrder.delivery_date == day,
            ExtraOrder.status.in_(BATCH_EXTRA_STATUSES),
        )
        if slot:
            subs = subs.filter(Order.meal_slot == slot)
            extras = extras.filter(ExtraOrder.meal_slot == slot)
        if lock:
            # one lock order everywhere (by id) so concurrent taps never deadlock
            subs = subs.order_by(Order.order_id).with_for_update()
            extras = extras.order_by(ExtraOrder.extra_order_id).with_for_update()
        return subs.all(), extras.all()

    @staticmethod
    def _batch_view(db: Session, vendor_id, day: date, slot: str) -> dict:
        subs, extras = ProviderOrderService._batch_rows(db, vendor_id, day, slot)
        ctx = MealContext(db, subs)
        items: dict = defaultdict(int)
        for o in subs:
            for pkg in ctx.packages(o):
                items[pkg["package_name"] or "Package"] += pkg["quantity"]
        names = _lookup(db, MenuPackage, "package_id", (e.package_reference_id for e in extras))
        live_extras = [e for e in extras if e.status != "pending"]
        for e in live_extras:
            pkg = names.get(e.package_reference_id)
            items[pkg.package_name if pkg else "Package"] += e.quantity
        rows = list(subs) + live_extras
        counts = {
            "total": len(rows),
            "to_prepare": sum(1 for r in rows if r.status in ("scheduled", "confirmed")),
            "preparing": sum(1 for r in rows if r.status == "preparing"),
            "ready_for_pickup": sum(1 for r in rows if r.status == "ready_for_pickup"),
            "awaiting_confirmation": sum(1 for e in extras if e.status == "pending"),
        }
        gone = db.query(Order.status, Order.cancel_reason).filter(
            Order.vendor_reference_id == vendor_id, Order.order_date == day, Order.meal_slot == slot,
            Order.status.in_(("skipped", "cancelled")),
        ).all()
        if counts["ready_for_pickup"] == counts["total"] and counts["total"]:
            state = "ready_for_pickup"
        elif counts["preparing"] or counts["ready_for_pickup"]:
            state = "preparing"
        else:
            state = "scheduled"
        is_today = day == today_local()
        return {
            "date": day,
            "meal_slot": slot,
            "delivery_window": delivery_window(slot),
            "status": state,
            "counts": counts,
            "excluded": {
                "skipped": sum(1 for s, _ in gone if s == "skipped"),
                "cancelled": sum(1 for s, r in gone if s == "cancelled" and r not in _HOLIDAY_REASONS),
                "holiday": sum(1 for s, r in gone if s == "cancelled" and r in _HOLIDAY_REASONS),
            },
            "item_summary": [{"package_name": n, "quantity": q} for n, q in sorted(items.items())],
            # any time, also before the delivery date
            "can_start_preparing": counts["to_prepare"] > 0,
            "can_mark_ready": (counts["to_prepare"] + counts["preparing"]) > 0,
            "is_today": is_today,
        }

    @staticmethod
    def next_batch(db: Session, vendor_id) -> dict:
        """
        The kitchen's next delivery batch (date + meal) that still has food to
        prepare, for the Home screen. A batch whose delivery window already
        ended today is overdue and is listed separately, so it never hides the
        next one.
        """
        today = today_local()
        horizon = today + timedelta(days=NEXT_BATCH_DAYS)
        keys = set()
        for day, slot in db.query(Order.order_date, Order.meal_slot).filter(
            Order.vendor_reference_id == vendor_id, Order.order_date >= today, Order.order_date <= horizon,
            Order.status.in_(("scheduled", "preparing")),
        ).distinct():
            keys.add((day, slot))
        for day, slot in db.query(ExtraOrder.delivery_date, ExtraOrder.meal_slot).filter(
            ExtraOrder.vendor_reference_id == vendor_id, ExtraOrder.delivery_date >= today,
            ExtraOrder.delivery_date <= horizon, ExtraOrder.status.in_(("pending", "confirmed", "preparing")),
        ).distinct():
            keys.add((day, slot))
        rank = {s: i for i, s in enumerate(SLOTS)}
        ordered = sorted(keys, key=lambda k: (k[0], rank.get(k[1], 9)))
        now = now_local()

        def overdue(key) -> bool:
            day, slot = key
            window = SLOT_WINDOWS.get(slot)
            return day == today and window is not None and now >= local_datetime(day, window[1])

        current = [k for k in ordered if not overdue(k)]
        closed_today = holidays.is_closed(db, vendor_id, today)
        return {
            "success": True,
            "today": today,
            "is_holiday_today": closed_today,
            "batch": ProviderOrderService._batch_view(db, vendor_id, *current[0]) if current else None,
            "upcoming": [
                {"date": d, "meal_slot": s, "delivery_window": delivery_window(s)} for d, s in current[1:4]
            ],
            "overdue_batches": [{"date": d, "meal_slot": s} for d, s in ordered if overdue((d, s))],
        }

    @staticmethod
    def update_batch(db: Session, vendor_id, day: date, slot: str, target: str) -> dict:
        """Start preparing / mark ready a whole batch in one transaction (idempotent)."""
        if slot not in SLOTS:
            raise DomainError(f"meal_slot must be one of: {', '.join(SLOTS)}", 422)
        if target not in ("preparing", "ready_for_pickup"):
            raise DomainError("status must be preparing or ready_for_pickup", 422)
        if target == "ready_for_pickup":
            result = ProviderOrderService._ready(db, vendor_id, day, slot)
        else:
            result = ProviderOrderService._start(db, vendor_id, day, slot)
        db.commit()
        return {**result, **ProviderOrderService.next_batch(db, vendor_id)}

    @staticmethod
    def _start(db: Session, vendor_id, day: date, slot: str) -> dict:
        subs, extras = ProviderOrderService._batch_rows(db, vendor_id, day, slot, lock=True)
        changed = 0
        for o in subs:
            if o.status == "scheduled":
                o.status = "preparing"
                changed += 1
                notify.customer(
                    db, o.user_reference_id, "order_status", "Your meal is being prepared",
                    f"Your {o.meal_slot} for {o.order_date} is being prepared.",
                    {"order_id": str(o.order_id), "kind": "subscription"},
                )
        for e in extras:
            if e.status == "confirmed":
                e.status = "preparing"
                changed += 1
                notify.customer(
                    db, e.user_reference_id, "order_status", "Your order is being prepared",
                    f"Your {e.meal_slot} order for {e.delivery_date} is preparing.",
                    {"order_id": str(e.extra_order_id), "kind": "extra"},
                )
        business_event("batch.preparing", provider_id=vendor_id, date=day, meal_slot=slot, changed=changed)
        return {
            "success": True,
            "message": f"{changed} order(s) are now being prepared" if changed else "Already being prepared",
            "changed": changed,
            "already_done": changed == 0,
        }

    @staticmethod
    def _ready(db: Session, vendor_id, day: date, slot: str | None) -> dict:
        """
        Every eligible meal of the batch (or of the day) becomes Ready for
        Pickup. Locked rows, one transaction: a double tap or a retry finds
        them ready and changes nothing, so nobody is notified twice. Each
        assigned partner gets one notice for all their meals.
        """
        if holidays.is_closed(db, vendor_id, day):
            raise DomainError(
                f"Your kitchen is on holiday {'today' if day == today_local() else f'on {day}'}, "
                "so there is nothing to mark ready.",
                409, code="KITCHEN_HOLIDAY",
            )
        subs, extras = ProviderOrderService._batch_rows(db, vendor_id, day, slot, lock=True)
        changed = []
        for o in subs:
            if o.status in KITCHEN_READY_FROM:
                _mark_ready(db, vendor_id, o, "subscription", notify_people=False)
                changed.append(("subscription", o))
        for e in extras:
            if e.status in ("confirmed", "preparing"):
                for line in _mark_ready(db, vendor_id, e, "extra", notify_people=False)["lines"]:
                    if all(line is not c[1] for c in changed):
                        changed.append(("extra", line))
        kitchen = db.query(Provider).filter(Provider.provider_id == vendor_id).first()
        kitchen_name = (kitchen.business_name if kitchen else None) or "The kitchen"
        where = kitchen_address(kitchen) or "the kitchen"
        by_partner: dict = defaultdict(list)
        unassigned = 0
        for kind, o in changed:
            if o.delivery_boy_reference_id:
                by_partner[o.delivery_boy_reference_id].append((kind, o))
            else:
                unassigned += 1
        for boy, rows in by_partner.items():
            slots = sorted({o.meal_slot for _, o in rows}, key=lambda s: SLOTS.index(s) if s in SLOTS else 9)
            notify.delivery_partner(
                db, boy, "order_ready", "Ready for pickup",
                f"{len(rows)} order(s) ({', '.join(slots)}) are packed at {kitchen_name}, {where}. "
                f"{_collect_text(day, plural=True)}",
                {
                    "provider_id": str(vendor_id), "kitchen_name": kitchen_name, "pickup_address": where,
                    "orders": [
                        {"order_id": str(o.order_id if kind == "subscription" else o.extra_order_id), "kind":
                         "subscription" if kind == "subscription" else "extra"}
                        for kind, o in rows
                    ],
                },
            )
        if unassigned:
            notify.kitchen(
                db, vendor_id, "pickup_pending", "Pickup pending - no delivery partner",
                f"{unassigned} packed order(s) have no delivery partner. Assign one from the order, "
                "or contact Orleeno support.",
                {"date": str(day), "meal_slot": slot},
            )
        business_event("batch.ready_for_pickup", provider_id=vendor_id, date=day, meal_slot=slot,
                       changed=len(changed), partners=len(by_partner))
        return {
            "success": True,
            "message": (f"{len(changed)} order(s) marked Ready for Pickup" if changed
                        else "Everything is already marked Ready for Pickup"),
            "changed": len(changed),
            "already_done": not changed,
            "partners_notified": len(by_partner),
        }

    @staticmethod
    def ready_today_preview(db: Session, vendor_id) -> dict:
        """The exact number of today's orders 'Mark all ready' would change (shown in the confirmation)."""
        today = today_local()
        if holidays.is_closed(db, vendor_id, today):
            return {"success": True, "date": today, "eligible": 0, "by_meal_slot": {}, "is_holiday_today": True}
        subs, extras = ProviderOrderService._batch_rows(db, vendor_id, today, None)
        eligible = [o for o in subs if o.status in KITCHEN_READY_FROM] + [
            e for e in extras if e.status in ("confirmed", "preparing")
        ]
        by_slot: dict = defaultdict(int)
        for o in eligible:
            by_slot[o.meal_slot] += 1
        return {
            "success": True,
            "date": today,
            "eligible": len(eligible),
            "by_meal_slot": dict(by_slot),
            "awaiting_confirmation": sum(1 for e in extras if e.status == "pending"),
            "is_holiday_today": False,
        }

    @staticmethod
    def ready_today(db: Session, vendor_id, expected: int | None = None) -> dict:
        today = today_local()
        result = ProviderOrderService._ready(db, vendor_id, today, None)
        db.commit()
        return {**result, "date": today, "expected": expected}
