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
delivery partner.
"""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.core.audit import business_event
from app.core.clock import today_local
from app.core.config import PICKUP_CODE_MAX_ATTEMPTS
from app.core.errors import DomainError
from app.domain import checkout, notify, orders as meals, partner_leave
from app.domain.status import (
    assert_sub_order_transition, assert_extra_order_transition, allowed_next,
    SUB_UNPICKED_STATUSES, EXTRA_UNPICKED_STATUSES, IN_HAND_STATUSES,
)
from app.domain.verification import pickup_code_row, pickup_code_value, regenerate_pickup_code
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


def _first_name(user: User | None) -> str | None:
    if user is None or not user.full_name:
        return None
    return user.full_name.split()[0]


def _sub_order_view(o: Order, packages, user, address, boy) -> dict:
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
        "next_actions": allowed_next("subscription", o.status, "provider"),
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
        "next_actions": allowed_next("extra", o.status, "provider"),
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
        view.update({
            "customer_name": _first_name(users.get(s.user_reference_id)),
            "delivery_area": f"{address.city} {address.pin_code}" if address else None,
            "delivery_boy_name": boy.full_name if boy else None,
            "packages": pkgs.get(s.subscription_id, []),
        })
        out.append(view)
    return out


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
        return {
            "success": True,
            "subscription": view,
            "orders": [
                _sub_order_view(
                    o, view["packages"], users.get(o.user_reference_id),
                    addresses.get(o.delivery_address_reference_id), boys.get(o.delivery_boy_reference_id),
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

        assert_sub_order_transition(order.status, new_status, "provider")
        if order.order_date > today_local():
            raise DomainError("Meals can only be prepared on their delivery date")

        order.status = new_status
        if new_status == "preparing":
            notify.customer(
                db, order.user_reference_id, "order_status", "Your meal is being prepared",
                f"Your {order.meal_slot} for {order.order_date} is being prepared.",
                {"order_id": str(order.order_id), "kind": "subscription"},
            )
        elif new_status == "ready_for_pickup":
            notify.delivery_partner(
                db, order.delivery_boy_reference_id, "order_ready", "Order ready for pickup",
                f"A {order.meal_slot} order is packed and ready at the kitchen. Ask for today's pickup code.",
                {"order_id": str(order.order_id), "kind": "subscription"},
            )
            _pickup_pending_without_partner(db, order, "subscription")
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

        assert_extra_order_transition(order.status, new_status, "provider")
        if new_status == "preparing" and order.delivery_date > today_local():
            raise DomainError("Orders can only be prepared on their delivery date")

        order.status = new_status
        if new_status == "ready_for_pickup":
            notify.delivery_partner(
                db, order.delivery_boy_reference_id, "order_ready", "Order ready for pickup",
                f"A one-time {order.meal_slot} order is packed and ready at the kitchen. Ask for today's pickup code.",
                {"order_id": str(order.extra_order_id), "kind": "extra"},
            )
            _pickup_pending_without_partner(db, order, "extra")
        elif new_status == "cancelled":
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
        if (
            boy is None
            or not boy.is_active
            or boy.approval_status != "approved"
            or (boy.assigned_provider_reference_id is not None and str(boy.assigned_provider_reference_id) != str(vendor_id))
        ):
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
        sub_q = db.query(Order).filter(
            Order.vendor_reference_id == vendor_id,
            Order.order_date == summary_date,
            Order.status.notin_(["cancelled", "skipped"]),
        )
        if meal_slot:
            sub_q = sub_q.filter(Order.meal_slot == meal_slot)
        sub_orders = sub_q.all()

        tally: dict = defaultdict(lambda: defaultdict(int))
        meal_counts: dict = defaultdict(int)

        if sub_orders:
            sub_ids = list({o.subscription_reference_id for o in sub_orders})
            sub_packages = db.query(SubscriptionPackage).filter(SubscriptionPackage.subscription_reference_id.in_(sub_ids)).all()
            sub_pkg_map: dict = defaultdict(list)
            for sp in sub_packages:
                sub_pkg_map[sp.subscription_reference_id].append((sp.package_reference_id, sp.quantity))
            package_ids = list({sp.package_reference_id for sp in sub_packages})
            items = db.query(MenuPackageItem).filter(MenuPackageItem.package_reference_id.in_(package_ids)).all()
            item_map: dict = defaultdict(list)
            for item in items:
                item_map[item.package_reference_id].append(item)
            for order in sub_orders:
                for pkg_id, qty in sub_pkg_map[order.subscription_reference_id]:
                    meal_counts[pkg_id] += qty
                    for item in item_map[pkg_id]:
                        tally[item.item_name][item.quantity or ""] += qty

        extra_q = db.query(ExtraOrder).filter(
            ExtraOrder.vendor_reference_id == vendor_id,
            ExtraOrder.delivery_date == summary_date,
            ExtraOrder.status != "cancelled",
        )
        if meal_slot:
            extra_q = extra_q.filter(ExtraOrder.meal_slot == meal_slot)
        extra_orders = extra_q.all()
        if extra_orders:
            ids = list({eo.package_reference_id for eo in extra_orders})
            items = db.query(MenuPackageItem).filter(MenuPackageItem.package_reference_id.in_(ids)).all()
            item_map = defaultdict(list)
            for item in items:
                item_map[item.package_reference_id].append(item)
            for eo in extra_orders:
                meal_counts[eo.package_reference_id] += eo.quantity
                for item in item_map[eo.package_reference_id]:
                    tally[item.item_name][item.quantity or ""] += eo.quantity

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
                {"item_name": name, "quantity_per_serving": qty_desc, "total_servings": total}
                for name in sorted(tally.keys())
                for qty_desc, total in tally[name].items()
            ],
        }
