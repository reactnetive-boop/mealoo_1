"""
Delivery partner order flow.

pickup:  only the assigned partner, on the order's date, after the kitchen
         has started preparing it, with the kitchen's pickup code.
deliver: only the assigned partner, only from out_for_delivery, with the
         customer's code. Wrong codes are counted; after
         DELIVERY_CODE_MAX_ATTEMPTS the order locks and needs admin help.
         The order row is locked, so concurrent or replayed requests cannot
         deliver (and pay) twice; settlement itself is idempotent too.
"""

from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import security_event, business_event
from app.core.clock import now_utc, today_local
from app.core.config import DELIVERY_CODE_MAX_ATTEMPTS
from app.core.errors import DomainError
from app.core.security import verify_code, hash_code
from app.domain import notify, orders as meals
from app.domain.status import assert_sub_order_transition, assert_extra_order_transition
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from app.repositories.delivery_boy_repository import DeliveryBoyRepository as Repo
from app.schemas.delivery_boy_schema import DeliveryBoyProfileResponse

HISTORY_MAX_DAYS = 31


def _codes_match(entered: str | None, expected: str | None) -> bool:
    if not expected:
        return False
    # constant-time comparison via the keyed hash
    return verify_code(entered or "", hash_code(expected))


def _date_window(on: date | None, from_date: date | None, to_date: date | None) -> tuple[date, date]:
    if on is not None:
        return on, on
    start = from_date or today_local()
    end = to_date or start
    if end < start:
        raise DomainError("to_date is before from_date")
    if (end - start).days > HISTORY_MAX_DAYS:
        raise DomainError(f"History is limited to {HISTORY_MAX_DAYS} days per request")
    return start, end


def _sub_view(o: Order) -> dict:
    return {
        "order_id": o.order_id,
        "subscription_reference_id": o.subscription_reference_id,
        "user_reference_id": o.user_reference_id,
        "vendor_reference_id": o.vendor_reference_id,
        "order_date": o.order_date,
        "meal_slot": o.meal_slot,
        "status": o.status,
        "is_free_skip": o.is_free_skip,
        "delivered_at": o.delivered_at,
        "picked_up_at": o.picked_up_at,
        "delivery_notes": o.delivery_notes,
        "delivery_locked": (o.delivery_code_attempts or 0) >= DELIVERY_CODE_MAX_ATTEMPTS,
        "created_at": o.created_at,
    }


def _extra_view(o: ExtraOrder) -> dict:
    return {
        "extra_order_id": o.extra_order_id,
        "user_reference_id": o.user_reference_id,
        "vendor_reference_id": o.vendor_reference_id,
        "package_reference_id": o.package_reference_id,
        "quantity": o.quantity,
        "unit_price": o.unit_price,
        "total_price": o.total_price,
        "delivery_date": o.delivery_date,
        "meal_slot": o.meal_slot,
        "status": o.status,
        "delivered_at": o.delivered_at,
        "picked_up_at": o.picked_up_at,
        "delivery_locked": (o.delivery_code_attempts or 0) >= DELIVERY_CODE_MAX_ATTEMPTS,
        "created_at": o.created_at,
    }


def _check_code(db: Session, order, entered: str | None, delivery_boy_id: str, ref: str) -> None:
    attempts = order.delivery_code_attempts or 0
    if attempts >= DELIVERY_CODE_MAX_ATTEMPTS:
        raise DomainError(
            "Too many wrong codes. This delivery is locked - please contact Orleeno support.",
            423,
            code="DELIVERY_LOCKED",
        )
    if not _codes_match(entered, order.otp_for_delivery):
        order.delivery_code_attempts = attempts + 1
        db.commit()
        security_event("delivery.code_failed", order=ref, delivery_boy_id=delivery_boy_id, attempts=order.delivery_code_attempts)
        left = DELIVERY_CODE_MAX_ATTEMPTS - order.delivery_code_attempts
        raise DomainError(f"Invalid delivery code. {left} attempt(s) left.", code="INVALID_DELIVERY_CODE")


class DeliveryBoyOrderService:

    # ── Profile ───────────────────────────────────────────

    @staticmethod
    def get_profile(db: Session, delivery_boy_id: str):
        boy = Repo.get_by_id(db, delivery_boy_id)
        if not boy:
            raise HTTPException(status_code=404, detail="Delivery boy not found")
        return {"success": True, "profile": DeliveryBoyProfileResponse.model_validate(boy)}

    @staticmethod
    def update_profile(db: Session, delivery_boy_id: str, payload):
        boy = Repo.get_by_id(db, delivery_boy_id)
        if not boy:
            raise HTTPException(status_code=404, detail="Delivery boy not found")

        update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
        if update_data.get("is_online") and (boy.approval_status != "approved" or not boy.is_active):
            raise DomainError("You can go online once your application is approved")
        if update_data.get("vehicle_number"):
            update_data["vehicle_number"] = update_data["vehicle_number"].strip().upper()
        boy = Repo.update(db, boy, update_data)
        return {
            "success": True,
            "message": "Profile updated",
            "profile": DeliveryBoyProfileResponse.model_validate(boy),
        }

    # ── Subscription meals ────────────────────────────────

    @staticmethod
    def list_orders(db: Session, delivery_boy_id: str, order_date: date = None, meal_slot: str = None,
                    status: str = None, from_date: date = None, to_date: date = None):
        start, end = _date_window(order_date, from_date, to_date)
        q = db.query(Order).filter(
            Order.delivery_boy_reference_id == delivery_boy_id,
            Order.order_date >= start,
            Order.order_date <= end,
        )
        if meal_slot:
            q = q.filter(Order.meal_slot == meal_slot)
        if status:
            q = q.filter(Order.status == status)
        orders = q.order_by(Order.order_date.asc(), Order.meal_slot.asc()).all()
        return {"success": True, "total": len(orders), "orders": [_sub_view(o) for o in orders]}

    @staticmethod
    def get_order_detail(db: Session, delivery_boy_id: str, order_id):
        row = Repo.get_subscription_order_detail(db, order_id, delivery_boy_id)
        if not row:
            raise HTTPException(status_code=404, detail="Order not found")
        order, user, address, subscription, vendor = row
        packages = [
            {"package_id": mp.package_id, "package_name": mp.package_name, "quantity": sp.quantity}
            for sp, mp in Repo.get_subscription_packages_for_order(db, subscription.subscription_id)
        ]
        return {
            "success": True,
            "order": _sub_view(order),
            "user": user,
            "delivery_address": address,
            "packages": packages,
            "vendor": vendor,
        }

    @staticmethod
    def pickup_order(db: Session, delivery_boy_id: str, order_id, payload):
        order = (
            db.query(Order)
            .filter(Order.order_id == order_id, Order.delivery_boy_reference_id == delivery_boy_id)
            .with_for_update()
            .first()
        )
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.order_date != today_local():
            raise DomainError("Orders can only be picked up on their delivery date")
        if order.status == "scheduled":
            raise DomainError("The kitchen has not started preparing this meal yet")
        assert_sub_order_transition(order.status, "out_for_delivery", "delivery_boy")
        if not _codes_match(payload.pickup_code, order.pickup_code):
            security_event("delivery.pickup_code_failed", order=order.order_id, delivery_boy_id=delivery_boy_id)
            raise DomainError("Invalid pickup code. Ask the kitchen for the code shown on the order.", code="INVALID_PICKUP_CODE")

        order.status = "out_for_delivery"
        order.picked_up_at = now_utc()
        if payload.delivery_notes:
            order.delivery_notes = payload.delivery_notes
        notify.customer(
            db, order.user_reference_id, "order_status", "Out for delivery",
            f"Your {order.meal_slot} is on the way. Share your delivery code with the delivery partner.",
            {"order_id": str(order.order_id), "kind": "subscription"},
        )
        db.commit()
        return {
            "success": True,
            "message": "Order picked up - marked as out for delivery",
            "order_id": order.order_id,
            "status": order.status,
        }

    @staticmethod
    def deliver_order(db: Session, delivery_boy_id: str, order_id, payload):
        order = (
            db.query(Order)
            .filter(Order.order_id == order_id, Order.delivery_boy_reference_id == delivery_boy_id)
            .with_for_update()
            .first()
        )
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.status == "delivered":
            # A retried request after success: nothing more to do
            return {"success": True, "message": "Order already delivered", "order_id": order.order_id, "status": order.status}
        assert_sub_order_transition(order.status, "delivered", "delivery_boy")
        _check_code(db, order, payload.otp, delivery_boy_id, str(order.order_id))

        order.status = "delivered"
        order.delivered_at = now_utc()
        if payload.delivery_notes:
            order.delivery_notes = payload.delivery_notes
        meals.settle_subscription_meal(db, order)
        notify.customer(
            db, order.user_reference_id, "order_status", "Delivered",
            f"Your {order.meal_slot} for {order.order_date} was delivered. Enjoy your meal!",
            {"order_id": str(order.order_id), "kind": "subscription"},
        )
        db.commit()
        business_event("order.delivered", order_id=order.order_id, delivery_boy_id=delivery_boy_id)
        return {"success": True, "message": "Order delivered successfully", "order_id": order.order_id, "status": order.status}

    # ── One-time orders ───────────────────────────────────

    @staticmethod
    def list_extra_orders(db: Session, delivery_boy_id: str, delivery_date: date = None, meal_slot: str = None,
                          status: str = None, from_date: date = None, to_date: date = None):
        start, end = _date_window(delivery_date, from_date, to_date)
        q = db.query(ExtraOrder).filter(
            ExtraOrder.delivery_boy_reference_id == delivery_boy_id,
            ExtraOrder.delivery_date >= start,
            ExtraOrder.delivery_date <= end,
        )
        if meal_slot:
            q = q.filter(ExtraOrder.meal_slot == meal_slot)
        if status:
            q = q.filter(ExtraOrder.status == status)
        orders = q.order_by(ExtraOrder.delivery_date.asc(), ExtraOrder.meal_slot.asc()).all()
        return {"success": True, "total": len(orders), "orders": [_extra_view(o) for o in orders]}

    @staticmethod
    def get_extra_order_detail(db: Session, delivery_boy_id: str, order_id):
        row = Repo.get_extra_order_detail(db, order_id, delivery_boy_id)
        if not row:
            raise HTTPException(status_code=404, detail="Extra order not found")
        order, user, address, package, vendor = row
        return {
            "success": True,
            "order": _extra_view(order),
            "user": user,
            "delivery_address": address,
            "package_name": package.package_name,
            "vendor": vendor,
        }

    @staticmethod
    def pickup_extra_order(db: Session, delivery_boy_id: str, order_id, payload):
        order = (
            db.query(ExtraOrder)
            .filter(ExtraOrder.extra_order_id == order_id, ExtraOrder.delivery_boy_reference_id == delivery_boy_id)
            .with_for_update()
            .first()
        )
        if not order:
            raise HTTPException(status_code=404, detail="Extra order not found")
        if order.delivery_date != today_local():
            raise DomainError("Orders can only be picked up on their delivery date")
        if order.status in ("pending", "confirmed"):
            raise DomainError("The kitchen has not started preparing this order yet")
        assert_extra_order_transition(order.status, "out_for_delivery", "delivery_boy")
        if not _codes_match(payload.pickup_code, order.pickup_code):
            security_event("delivery.pickup_code_failed", order=order.extra_order_id, delivery_boy_id=delivery_boy_id)
            raise DomainError("Invalid pickup code. Ask the kitchen for the code shown on the order.", code="INVALID_PICKUP_CODE")

        order.status = "out_for_delivery"
        order.picked_up_at = now_utc()
        notify.customer(
            db, order.user_reference_id, "order_status", "Out for delivery",
            f"Your {order.meal_slot} order is on the way. Share your delivery code with the delivery partner.",
            {"order_id": str(order.extra_order_id), "kind": "extra"},
        )
        db.commit()
        return {
            "success": True,
            "message": "Extra order picked up - marked as out for delivery",
            "order_id": order.extra_order_id,
            "status": order.status,
        }

    @staticmethod
    def deliver_extra_order(db: Session, delivery_boy_id: str, order_id, payload):
        order = (
            db.query(ExtraOrder)
            .filter(ExtraOrder.extra_order_id == order_id, ExtraOrder.delivery_boy_reference_id == delivery_boy_id)
            .with_for_update()
            .first()
        )
        if not order:
            raise HTTPException(status_code=404, detail="Extra order not found")
        if order.status == "delivered":
            return {"success": True, "message": "Order already delivered", "order_id": order.extra_order_id, "status": order.status}
        assert_extra_order_transition(order.status, "delivered", "delivery_boy")
        _check_code(db, order, payload.otp, delivery_boy_id, str(order.extra_order_id))

        order.status = "delivered"
        order.delivered_at = now_utc()
        meals.settle_extra_order(db, order)
        notify.customer(
            db, order.user_reference_id, "order_status", "Delivered",
            f"Your {order.meal_slot} order for {order.delivery_date} was delivered.",
            {"order_id": str(order.extra_order_id), "kind": "extra"},
        )
        db.commit()
        business_event("extra_order.delivered", order_id=order.extra_order_id, delivery_boy_id=delivery_boy_id)
        return {"success": True, "message": "Extra order delivered successfully", "order_id": order.extra_order_id, "status": order.status}
