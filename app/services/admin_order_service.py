"""
Admin operations on orders.

Forced status changes go through the same state machine as everyone else
(actor "admin") and carry their money effects: forcing 'delivered' settles
the kitchen / partner / platform once, forcing 'cancelled' refunds the
customer once. Every forced change needs a reason and is audited.
"""

from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import record_audit, business_event
from app.core.clock import now_utc, today_local
from app.core.errors import DomainError
from app.core.security import generate_numeric_code
from app.domain import capacity, notify
from app.domain import orders as meals
from app.domain.eligibility import is_on_holiday, parse_pincode, provider_block_reason
from app.domain.slots import is_before_cutoff
from app.domain.status import (
    assert_sub_order_transition,
    assert_extra_order_transition,
    SUB_ORDER_STATUSES,
    EXTRA_ORDER_STATUSES,
    SUBSCRIPTION_STATUSES,
)
from app.models.delivery_boy_model import DeliveryBoy
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.subscription_model import Subscription
from app.models.user_address_model import UserAddress
from app.services.admin_views import order_admin_view, extra_order_admin_view, subscription_admin_view

SUB_ASSIGNABLE = ("scheduled", "preparing")
EXTRA_ASSIGNABLE = ("pending", "confirmed", "preparing")


def _sub_order(db: Session, order_id) -> Order:
    order = db.query(Order).filter(Order.order_id == order_id).with_for_update().first()
    if not order:
        raise HTTPException(status_code=404, detail="Subscription order not found")
    return order


def _extra_order(db: Session, order_id) -> ExtraOrder:
    order = db.query(ExtraOrder).filter(ExtraOrder.extra_order_id == order_id).with_for_update().first()
    if not order:
        raise HTTPException(status_code=404, detail="Extra order not found")
    return order


def _partner(db: Session, delivery_boy_id) -> DeliveryBoy:
    boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == delivery_boy_id).first()
    if not boy:
        raise HTTPException(status_code=404, detail="Delivery partner not found")
    if not boy.is_active or boy.approval_status != "approved":
        raise DomainError("This delivery partner is not active and approved")
    return boy


def _check_status_filter(status: str | None, allowed) -> None:
    if status and status not in allowed:
        raise DomainError(f"status must be one of: {', '.join(allowed)}")


def _new_kitchen(db: Session, new_provider_id: str, current_provider_id, on: date, slot: str, address_id) -> Provider:
    if str(current_provider_id) == new_provider_id:
        raise DomainError("New provider is the same as the current provider.")
    provider = db.query(Provider).filter(Provider.provider_id == new_provider_id).with_for_update().first()
    if provider is None:
        raise HTTPException(status_code=404, detail="New provider not found")
    reason = provider_block_reason(provider)
    if reason:
        raise DomainError(f"New kitchen cannot take orders: {reason}")
    if is_on_holiday(db, provider.provider_id, on):
        raise DomainError(f"New kitchen is on holiday on {on}.")
    address = db.query(UserAddress).filter(UserAddress.user_address_id == address_id).first()
    if address is not None and parse_pincode(address.pin_code) != provider.pincode:
        raise DomainError("New kitchen does not deliver to this customer's pincode.")
    if not is_before_cutoff(on, slot):
        raise DomainError(f"The {slot} cut-off for {on} has passed; the order can no longer be moved.")
    return provider


class AdminOrderService:

    # ── Lists ─────────────────────────────────────────────

    @staticmethod
    def list_subscription_orders(db: Session, vendor_id: str = None, user_id: str = None,
                                 order_date: date = None, status: str = None,
                                 page: int = 1, limit: int = 50):
        _check_status_filter(status, SUB_ORDER_STATUSES)
        query = db.query(Order)
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
        return {"success": True, "total": total, "page": page, "orders": [order_admin_view(o) for o in orders]}

    @staticmethod
    def list_extra_orders(db: Session, vendor_id: str = None, user_id: str = None,
                          delivery_date: date = None, status: str = None,
                          page: int = 1, limit: int = 50):
        _check_status_filter(status, EXTRA_ORDER_STATUSES)
        query = db.query(ExtraOrder)
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
        return {"success": True, "total": total, "page": page, "orders": [extra_order_admin_view(o) for o in orders]}

    @staticmethod
    def list_subscriptions(db: Session, vendor_id: str = None, user_id: str = None,
                           status: str = None, page: int = 1, limit: int = 20):
        _check_status_filter(status, SUBSCRIPTION_STATUSES)
        query = db.query(Subscription)
        if vendor_id:
            query = query.filter(Subscription.vendor_reference_id == vendor_id)
        if user_id:
            query = query.filter(Subscription.user_reference_id == user_id)
        if status:
            query = query.filter(Subscription.status == status)

        total = query.count()
        subs = query.order_by(Subscription.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page, "subscriptions": [subscription_admin_view(s) for s in subs]}

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

        previous_id = order.delivery_boy_reference_id
        order.delivery_boy_reference_id = boy.delivery_boy_id
        order_key = "order_id" if kind == "subscription" else "extra_order_id"
        oid = getattr(order, order_key)

        notify.delivery_partner(
            db, boy.delivery_boy_id, "order_assigned", "New delivery assigned",
            f"{order.meal_slot.title()} delivery on {on}.",
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
        # the old kitchen saw the pickup code; the new one gets a fresh code and picks its own partner
        order.pickup_code = generate_numeric_code(meals.PICKUP_CODE_LENGTH)
        order.delivery_boy_reference_id = None

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
        capacity.assert_kitchen_room(
            db, provider_id=provider.provider_id, slots=[order.meal_slot],
            start=order.delivery_date, end=order.delivery_date, quantity=order.quantity,
        )

        previous_provider_id = str(order.vendor_reference_id)
        order.vendor_reference_id = provider.provider_id
        order.pickup_code = generate_numeric_code(meals.PICKUP_CODE_LENGTH)
        order.delivery_boy_reference_id = None
        # the new kitchen confirms it again
        order.status = "pending"

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
