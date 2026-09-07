from datetime import date, datetime, timezone, timedelta, time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.order_model import Order
from app.models.extra_order_model import ExtraOrder
from app.models.subscription_model import Subscription
from app.models.delivery_boy_model import DeliveryBoy
from app.models.provider_model import Provider
from app.models.provider_unavailability_model import ProviderUnavailability

IST = timezone(timedelta(hours=5, minutes=30))

# Cutoff times (IST) after which admin cannot reassign a same-day order
MEAL_CUTOFF_IST: dict[str, time] = {
    "breakfast": time(7, 0),
    "lunch": time(9, 0),
    "dinner": time(15, 0),
    "both": time(9, 0),   # combined slot — use lunch cutoff
    "all": time(9, 0),
    "all_day": time(9, 0),
}


def _check_reassign_cutoff(order_date: date, meal_slot: str) -> None:
    today_ist = datetime.now(IST).date()
    if order_date != today_ist:
        return  # future or past orders are always reassignable
    cutoff = MEAL_CUTOFF_IST.get(meal_slot, time(9, 0))
    now_ist = datetime.now(IST).time()
    if now_ist >= cutoff:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cutoff time for '{meal_slot}' orders has passed. "
                f"Reassignment must happen before {cutoff.strftime('%I:%M %p')} IST on the delivery day."
            )
        )


SUB_ORDER_STATUSES = {"scheduled", "preparing", "out_for_delivery", "delivered", "skipped", "cancelled"}
EXTRA_ORDER_STATUSES = {"pending", "confirmed", "preparing", "out_for_delivery", "delivered", "cancelled"}


class AdminOrderService:

    @staticmethod
    def list_subscription_orders(db: Session, vendor_id: str = None, user_id: str = None,
                                 order_date: date = None, status: str = None,
                                 page: int = 1, limit: int = 50):
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
        return {"success": True, "total": total, "page": page, "orders": orders}

    @staticmethod
    def list_extra_orders(db: Session, vendor_id: str = None, user_id: str = None,
                          delivery_date: date = None, status: str = None,
                          page: int = 1, limit: int = 50):
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
        return {"success": True, "total": total, "page": page, "orders": orders}

    @staticmethod
    def force_update_order_status(db: Session, order_id: str, payload):
        if payload.status not in SUB_ORDER_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(SUB_ORDER_STATUSES)}")

        order = db.query(Order).filter(Order.order_id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        order.status = payload.status
        db.commit()
        return {"success": True, "message": f"Order status forced to '{payload.status}'", "order_id": order_id}

    @staticmethod
    def force_update_extra_order_status(db: Session, order_id: str, payload):
        if payload.status not in EXTRA_ORDER_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(EXTRA_ORDER_STATUSES)}")

        order = db.query(ExtraOrder).filter(ExtraOrder.extra_order_id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Extra order not found")

        order.status = payload.status
        db.commit()
        return {"success": True, "message": f"Extra order status forced to '{payload.status}'", "order_id": order_id}

    @staticmethod
    def assign_delivery_boy(db: Session, order_id: str, payload):
        TERMINAL = {"delivered", "cancelled", "skipped"}

        order = db.query(Order).filter(Order.order_id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Subscription order not found")
        if order.status in TERMINAL:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot assign delivery boy to an order with status '{order.status}'."
            )

        boy = db.query(DeliveryBoy).filter(
            DeliveryBoy.delivery_boy_id == payload.delivery_boy_id
        ).first()
        if not boy:
            raise HTTPException(status_code=404, detail="Delivery boy not found")
        if not boy.is_active:
            raise HTTPException(status_code=400, detail="Delivery boy is not active")

        previous_id = order.delivery_boy_reference_id
        order.delivery_boy_reference_id = payload.delivery_boy_id
        db.commit()

        action = "reassigned" if previous_id else "assigned"
        return {
            "success": True,
            "message": f"Delivery boy {action} successfully",
            "order_id": order_id,
            "delivery_boy_id": str(payload.delivery_boy_id),
            "previous_delivery_boy_id": str(previous_id) if previous_id else None,
        }

    @staticmethod
    def assign_extra_delivery_boy(db: Session, order_id: str, payload):
        TERMINAL = {"delivered", "cancelled"}

        order = db.query(ExtraOrder).filter(ExtraOrder.extra_order_id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Extra order not found")
        if order.status in TERMINAL:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot assign delivery boy to an order with status '{order.status}'."
            )

        boy = db.query(DeliveryBoy).filter(
            DeliveryBoy.delivery_boy_id == payload.delivery_boy_id
        ).first()
        if not boy:
            raise HTTPException(status_code=404, detail="Delivery boy not found")
        if not boy.is_active:
            raise HTTPException(status_code=400, detail="Delivery boy is not active")

        previous_id = order.delivery_boy_reference_id
        order.delivery_boy_reference_id = payload.delivery_boy_id
        db.commit()

        action = "reassigned" if previous_id else "assigned"
        return {
            "success": True,
            "message": f"Delivery boy {action} successfully",
            "order_id": order_id,
            "delivery_boy_id": str(payload.delivery_boy_id),
            "previous_delivery_boy_id": str(previous_id) if previous_id else None,
        }

    @staticmethod
    def reassign_provider(db: Session, order_id: str, payload):
        TERMINAL = {"delivered", "cancelled", "skipped"}

        order = db.query(Order).filter(Order.order_id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Subscription order not found")
        if order.status in TERMINAL:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reassign a '{order.status}' order."
            )

        new_provider_id = str(payload.new_provider_id)
        if str(order.vendor_reference_id) == new_provider_id:
            raise HTTPException(status_code=400, detail="New provider is the same as the current provider.")

        # Current provider must be marked unavailable for this order date
        current_unavailable = db.query(ProviderUnavailability).filter(
            ProviderUnavailability.provider_reference_id == str(order.vendor_reference_id),
            ProviderUnavailability.unavailable_date == order.order_date
        ).first()
        if not current_unavailable:
            raise HTTPException(
                status_code=400,
                detail="Current provider must be marked unavailable for this date before reassigning."
            )

        # New provider must exist, be active, and be accepting orders
        new_provider = db.query(Provider).filter(Provider.provider_id == new_provider_id).first()
        if not new_provider:
            raise HTTPException(status_code=404, detail="New provider not found")
        if not new_provider.is_active:
            raise HTTPException(status_code=400, detail="New provider is not active.")
        if not new_provider.is_accepting_orders:
            raise HTTPException(status_code=400, detail="New provider is not accepting orders.")

        # New provider must not be marked unavailable for this date
        new_unavailable = db.query(ProviderUnavailability).filter(
            ProviderUnavailability.provider_reference_id == new_provider_id,
            ProviderUnavailability.unavailable_date == order.order_date
        ).first()
        if new_unavailable:
            raise HTTPException(
                status_code=400,
                detail=f"New provider is also marked unavailable on {order.order_date}."
            )

        # Enforce cutoff: only for same-day orders
        _check_reassign_cutoff(order.order_date, order.meal_slot)

        previous_provider_id = str(order.vendor_reference_id)
        order.vendor_reference_id = payload.new_provider_id
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
    def reassign_extra_order_provider(db: Session, order_id: str, payload):
        TERMINAL = {"delivered", "cancelled"}

        order = db.query(ExtraOrder).filter(ExtraOrder.extra_order_id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Extra order not found")
        if order.status in TERMINAL:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reassign a '{order.status}' order."
            )

        new_provider_id = str(payload.new_provider_id)
        if str(order.vendor_reference_id) == new_provider_id:
            raise HTTPException(status_code=400, detail="New provider is the same as the current provider.")

        # Current provider must be marked unavailable for the delivery date
        current_unavailable = db.query(ProviderUnavailability).filter(
            ProviderUnavailability.provider_reference_id == str(order.vendor_reference_id),
            ProviderUnavailability.unavailable_date == order.delivery_date
        ).first()
        if not current_unavailable:
            raise HTTPException(
                status_code=400,
                detail="Current provider must be marked unavailable for this date before reassigning."
            )

        # New provider must exist, be active, and be accepting orders
        new_provider = db.query(Provider).filter(Provider.provider_id == new_provider_id).first()
        if not new_provider:
            raise HTTPException(status_code=404, detail="New provider not found")
        if not new_provider.is_active:
            raise HTTPException(status_code=400, detail="New provider is not active.")
        if not new_provider.is_accepting_orders:
            raise HTTPException(status_code=400, detail="New provider is not accepting orders.")

        # New provider must not be unavailable for the delivery date
        new_unavailable = db.query(ProviderUnavailability).filter(
            ProviderUnavailability.provider_reference_id == new_provider_id,
            ProviderUnavailability.unavailable_date == order.delivery_date
        ).first()
        if new_unavailable:
            raise HTTPException(
                status_code=400,
                detail=f"New provider is also marked unavailable on {order.delivery_date}."
            )

        # Enforce cutoff: only for same-day orders
        _check_reassign_cutoff(order.delivery_date, order.meal_slot)

        previous_provider_id = str(order.vendor_reference_id)
        order.vendor_reference_id = payload.new_provider_id
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

    @staticmethod
    def list_subscriptions(db: Session, vendor_id: str = None, user_id: str = None,
                           status: str = None, page: int = 1, limit: int = 20):
        query = db.query(Subscription)
        if vendor_id:
            query = query.filter(Subscription.vendor_reference_id == vendor_id)
        if user_id:
            query = query.filter(Subscription.user_reference_id == user_id)
        if status:
            query = query.filter(Subscription.status == status)

        total = query.count()
        subs = query.order_by(Subscription.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page, "subscriptions": subs}
