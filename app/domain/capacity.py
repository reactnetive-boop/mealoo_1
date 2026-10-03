"""
Date-aware daily limits.

Two limits apply per meal slot per day and an order must fit both:
  * package daily capacity (provider_selected_packages.daily_capacity)
  * kitchen daily meal limit (providers.daily_meal_quota)

Demand on a date is counted from the actual meal rows of that date (not from
"active subscriptions"), so paused meals, skips and cancellations free
capacity, and future-dated subscriptions only count on their own dates.

Callers lock the kitchen row (eligibility.assert_sellable(lock_provider=True))
before checking, so two concurrent orders cannot both take the last slot.
"""

from collections import defaultdict
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.provider_selected_package_model import ProviderSelectedPackage
from app.models.subscription_package_model import SubscriptionPackage
from app.domain.slots import SLOTS

_LIVE_SUB = ("scheduled", "preparing", "out_for_delivery", "delivered")
_LIVE_EXTRA = ("pending", "confirmed", "preparing", "out_for_delivery", "delivered")


def _subscription_demand(db: Session, provider_id, slot: str, start: date, end: date, package_id=None) -> dict:
    q = (
        db.query(Order.order_date, func.coalesce(func.sum(SubscriptionPackage.quantity), 0))
        .join(SubscriptionPackage, SubscriptionPackage.subscription_reference_id == Order.subscription_reference_id)
        .filter(
            Order.vendor_reference_id == provider_id,
            Order.meal_slot == slot,
            Order.order_date >= start,
            Order.order_date <= end,
            Order.status.in_(_LIVE_SUB),
        )
    )
    if package_id is not None:
        q = q.filter(SubscriptionPackage.package_reference_id == package_id)
    return {d: int(n) for d, n in q.group_by(Order.order_date).all()}


def _extra_demand(db: Session, provider_id, slot: str, start: date, end: date, package_id=None) -> dict:
    q = (
        db.query(ExtraOrder.delivery_date, func.coalesce(func.sum(ExtraOrder.quantity), 0))
        .filter(
            ExtraOrder.vendor_reference_id == provider_id,
            ExtraOrder.meal_slot == slot,
            ExtraOrder.delivery_date >= start,
            ExtraOrder.delivery_date <= end,
            ExtraOrder.status.in_(_LIVE_EXTRA),
        )
    )
    if package_id is not None:
        q = q.filter(ExtraOrder.package_reference_id == package_id)
    return {d: int(n) for d, n in q.group_by(ExtraOrder.delivery_date).all()}


def committed(db: Session, provider_id, slot: str, start: date, end: date, package_id=None) -> dict:
    """date -> meals already committed for this kitchen (and package)."""
    total: dict = defaultdict(int)
    for source in (_subscription_demand, _extra_demand):
        for d, n in source(db, provider_id, slot, start, end, package_id).items():
            total[d] += n
    return total


def package_capacity(db: Session, provider_id, package_id) -> int | None:
    row = (
        db.query(ProviderSelectedPackage.daily_capacity)
        .filter(
            ProviderSelectedPackage.provider_id == provider_id,
            ProviderSelectedPackage.package_id == package_id,
            ProviderSelectedPackage.is_active == True,  # noqa: E712
        )
        .first()
    )
    return int(row[0]) if row and row[0] is not None else None


def kitchen_quota(db: Session, provider_id) -> int | None:
    row = db.query(Provider.daily_meal_quota).filter(Provider.provider_id == provider_id).first()
    return int(row[0]) if row and row[0] is not None else None


def assert_room(
    db: Session,
    *,
    provider_id,
    package_id,
    package_name: str,
    slots: list[str],
    start: date,
    end: date,
    quantity: int,
) -> None:
    """Raise if adding `quantity` meals per slot on every date in [start, end] overflows a limit."""

    assert_package_room(
        db, provider_id=provider_id, package_id=package_id, package_name=package_name,
        slots=slots, start=start, end=end, quantity=quantity,
    )
    assert_kitchen_room(db, provider_id=provider_id, slots=slots, start=start, end=end, quantity=quantity)


def assert_package_room(db: Session, *, provider_id, package_id, package_name: str, slots, start: date, end: date, quantity: int) -> None:
    cap = package_capacity(db, provider_id, package_id)
    if cap is None:
        return
    for slot in slots:
        used = committed(db, provider_id, slot, start, end, package_id)
        peak_day, peak = max(used.items(), key=lambda kv: kv[1], default=(start, 0))
        if peak + quantity > cap:
            raise DomainError(
                f"Package '{package_name}' has reached its daily capacity for {slot} "
                f"on {peak_day}. Limit {cap}, already booked {peak}, requested {quantity}.",
                code="CAPACITY_FULL",
            )


def assert_kitchen_room(db: Session, *, provider_id, slots, start: date, end: date, quantity: int) -> None:
    quota = kitchen_quota(db, provider_id)
    if quota is None:
        return
    for slot in slots:
        used = committed(db, provider_id, slot, start, end)
        peak_day, peak = max(used.items(), key=lambda kv: kv[1], default=(start, 0))
        if peak + quantity > quota:
            raise DomainError(
                f"This kitchen has reached its daily meal limit for {slot} on {peak_day}. "
                f"Limit {quota}, already booked {peak}, requested {quantity}.",
                code="DAILY_LIMIT_FULL",
            )


def quota_status(db: Session, provider_id, on: date) -> dict:
    quota = kitchen_quota(db, provider_id)
    slots = {}
    for slot in SLOTS:
        sub = _subscription_demand(db, provider_id, slot, on, on).get(on, 0)
        extra = _extra_demand(db, provider_id, slot, on, on).get(on, 0)
        total = sub + extra
        slots[slot] = {
            "subscription_committed": sub,
            "extra_orders": extra,
            "total_committed": total,
            "available": max(0, quota - total) if quota is not None else None,
            "is_full": quota is not None and total >= quota,
        }
    return {"daily_meal_quota": quota, "date": on, "slots": slots}


def peak_future_demand(db: Session, provider_id, from_date: date, package_id=None) -> int:
    """Highest committed meals on any single future date and slot."""
    far = date(from_date.year + 2, 12, 31)
    peak = 0
    for slot in SLOTS:
        used = committed(db, provider_id, slot, from_date, far, package_id)
        if used:
            peak = max(peak, max(used.values()))
    return peak
