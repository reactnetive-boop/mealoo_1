"""
Delivery partner leave days.

A partner (or Orleeno for them) marks a date off. From then on:
  * that day's open deliveries are released (no partner) and each kitchen is
    told to assign someone else; admins see them as unassigned;
  * meals generated or assigned for that day never go to the partner, even
    when their subscription is assigned to them;
  * nobody can assign them an order for that day.
Cancelling the leave gives the partner back their subscription meals of that
day that are still open and unassigned.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.core.errors import DomainError
from app.domain import notify
from app.domain.status import EXTRA_UNPICKED_STATUSES, SUB_UNPICKED_STATUSES
from app.models.delivery_boy_leave_model import DeliveryBoyLeave
from app.models.delivery_boy_model import DeliveryBoy
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from app.models.subscription_model import Subscription

MAX_DAYS_AHEAD = 60


def leave_dates(db: Session, delivery_boy_id, start: date, end: date) -> set:
    if delivery_boy_id is None:
        return set()
    rows = db.query(DeliveryBoyLeave.leave_date).filter(
        DeliveryBoyLeave.delivery_boy_reference_id == delivery_boy_id,
        DeliveryBoyLeave.leave_date >= start,
        DeliveryBoyLeave.leave_date <= end,
    ).all()
    return {r[0] for r in rows}


def on_leave(db: Session, delivery_boy_id, day: date) -> bool:
    return bool(leave_dates(db, delivery_boy_id, day, day))


def assert_available(db: Session, delivery_boy_id, day: date) -> None:
    if on_leave(db, delivery_boy_id, day):
        raise DomainError(f"This delivery partner is on leave on {day}", code="PARTNER_ON_LEAVE")


def _view(row: DeliveryBoyLeave) -> dict:
    return {"leave_date": row.leave_date, "reason": row.reason, "created_by": row.created_by_type,
            "created_at": row.created_at}


def list_leaves(db: Session, delivery_boy_id, include_past: bool = False) -> dict:
    q = db.query(DeliveryBoyLeave).filter(DeliveryBoyLeave.delivery_boy_reference_id == delivery_boy_id)
    if not include_past:
        q = q.filter(DeliveryBoyLeave.leave_date >= today_local())
    return {"success": True, "leaves": [_view(r) for r in q.order_by(DeliveryBoyLeave.leave_date).all()]}


def add_leave(db: Session, delivery_boy_id, day: date, reason: str | None, by: str) -> dict:
    today = today_local()
    if day < today:
        raise DomainError("Leave cannot be added for a past date")
    if (day - today).days > MAX_DAYS_AHEAD:
        raise DomainError(f"Leave can be planned at most {MAX_DAYS_AHEAD} days ahead")
    boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == delivery_boy_id).with_for_update().first()
    if boy is None:
        raise DomainError("Delivery partner not found", 404)
    if on_leave(db, delivery_boy_id, day):
        raise DomainError(f"Already on leave on {day}", 409)

    db.add(DeliveryBoyLeave(delivery_boy_reference_id=delivery_boy_id, leave_date=day, reason=reason,
                            created_by_type=by))
    released = 0
    kitchens: dict = {}
    for model, day_col, statuses, kind in (
        (Order, Order.order_date, SUB_UNPICKED_STATUSES, "subscription"),
        (ExtraOrder, ExtraOrder.delivery_date, EXTRA_UNPICKED_STATUSES, "extra"),
    ):
        rows = db.query(model).filter(
            model.delivery_boy_reference_id == delivery_boy_id, day_col == day, model.status.in_(statuses)
        ).with_for_update().all()
        for order in rows:
            order.delivery_boy_reference_id = None
            kitchens[order.vendor_reference_id] = kitchens.get(order.vendor_reference_id, 0) + 1
            released += 1
    for provider_id, count in kitchens.items():
        notify.kitchen(
            db, provider_id, "partner_unassigned", "Delivery partner on leave",
            f"{boy.full_name or 'A delivery partner'} is on leave on {day}. "
            f"{count} order(s) need another partner - assign one or contact Orleeno.",
            {"date": str(day)},
        )
    db.commit()
    return {
        "success": True,
        "message": f"Leave added for {day}." + (f" {released} delivery(ies) were handed back." if released else ""),
        "released_orders": released,
    }


def cancel_leave(db: Session, delivery_boy_id, day: date) -> dict:
    if day < today_local():
        raise DomainError("Past leave cannot be changed")
    row = db.query(DeliveryBoyLeave).filter(
        DeliveryBoyLeave.delivery_boy_reference_id == delivery_boy_id, DeliveryBoyLeave.leave_date == day
    ).first()
    if row is None:
        raise DomainError("No leave on that date", 404)
    db.delete(row)
    # their own subscriptions' meals that nobody picked up in the meantime come back
    restored = (
        db.query(Order)
        .join(Subscription, Subscription.subscription_id == Order.subscription_reference_id)
        .filter(
            Subscription.delivery_boy_reference_id == delivery_boy_id,
            Order.order_date == day,
            Order.delivery_boy_reference_id.is_(None),
            Order.status.in_(SUB_UNPICKED_STATUSES),
        )
        .with_for_update(of=Order)
        .all()
    )
    for meal in restored:
        meal.delivery_boy_reference_id = delivery_boy_id
    db.commit()
    return {"success": True, "message": f"Leave on {day} cancelled", "restored_meals": len(restored)}
