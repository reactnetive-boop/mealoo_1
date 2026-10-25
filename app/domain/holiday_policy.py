"""
Casual holidays added after subscriptions were sold.

When a kitchen plans a holiday (from tomorrow on) its running subscriptions
are re-planned in the same transaction:

  * the meals still to come on each new holiday date are cancelled with
    cancel_reason 'vendor_holiday' (never refunded: they are made up);
  * the subscription is extended by one open day of the kitchen per holiday
    date that had a meal owed, so no paid meal is lost (when only some meals
    of that day were still owed - the customer skipped the others - the
    make-up day carries only the owed ones);
  * the date joins subscriptions.holiday_dates and the customer is told in
    advance (one notice per holiday and subscription).

Dates a subscription already treats as holidays are skipped, so overlapping
or repeated rules never re-plan the same day twice. Removing a holiday later
does not shorten any subscription (its meal count is already right).
"""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.audit import business_event
from app.core.clock import today_local
from app.domain import holidays, notify, orders as meals
from app.domain.slots import expand_plan_slot
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.subscription_model import Subscription
from app.models.vendor_holiday_model import VendorHoliday

RUNNING = ("active", "paused")
REASON = "vendor_holiday"
NOT_OWED_REASON = "vendor_holiday_not_owed"
# Meals still at the kitchen: casual holidays start tomorrow at the earliest, and a kitchen
# may start or pack a meal ahead of its date, so all of these are re-planned.
_AT_KITCHEN = ("scheduled", "preparing", "ready_for_pickup")


def _future_rule_dates(h: VendorHoliday, sub: Subscription, first: date) -> list[date]:
    lo = max(first, sub.start_date)
    hi = sub.end_date - timedelta(days=1)
    return sorted(holidays.rule_dates(h, lo, hi)) if lo <= hi else []


def affected(db: Session, h: VendorHoliday) -> list[tuple[Subscription, list[date]]]:
    """Running subscriptions of the kitchen with at least one new holiday date inside their span."""
    first = today_local() + timedelta(days=1)
    subs = (
        db.query(Subscription)
        .filter(
            Subscription.vendor_reference_id == h.provider_reference_id,
            Subscription.status.in_(RUNNING),
            Subscription.end_date > first,
        )
        .order_by(Subscription.subscription_id)
        .all()
    )
    out = []
    for sub in subs:
        known = holidays.sub_holidays(sub)
        dates = [d for d in _future_rule_dates(h, sub, first) if d not in known]
        if dates:
            out.append((sub, dates))
    return out


def preview(db: Session, h: VendorHoliday) -> dict:
    """What adding this (not yet saved) rule would change: affected subscriptions and meals."""
    rows = affected(db, h)
    meal_count = 0
    for sub, dates in rows:
        meal_count += db.query(Order).filter(
            Order.subscription_reference_id == sub.subscription_id,
            Order.order_date.in_(dates),
            Order.status.in_(_AT_KITCHEN),
        ).count()
    first = today_local() + timedelta(days=1)
    upcoming = sorted(holidays.rule_dates(h, first, first + timedelta(days=60)))
    return {
        "affected_subscriptions": len(rows),
        "affected_meals": meal_count,
        "upcoming_dates": [d.isoformat() for d in upcoming[:20]],
    }


def _not_owed_row(sub: Subscription, on: date, slot: str) -> dict:
    return {
        "subscription_reference_id": sub.subscription_id,
        "user_reference_id": sub.user_reference_id,
        "vendor_reference_id": sub.vendor_reference_id,
        "delivery_address_reference_id": sub.user_address_reference_id,
        "order_date": on,
        "meal_slot": slot,
        "status": "cancelled",
        "cancel_reason": NOT_OWED_REASON,
        "is_free_skip": False,
        **meals.new_codes(),
    }


def apply(db: Session, h: VendorHoliday) -> dict:
    """Re-plan every running subscription the holiday touches (caller commits)."""
    kitchen = db.query(Provider).filter(Provider.provider_id == h.provider_reference_id).first()
    kitchen_name = (kitchen.business_name if kitchen else None) or "Your kitchen"
    partners: dict = defaultdict(set)
    touched = 0
    cancelled_total = 0
    for sub, dates in affected(db, h):
        sub = db.query(Subscription).filter(
            Subscription.subscription_id == sub.subscription_id
        ).with_for_update().populate_existing().one()
        slots = expand_plan_slot(sub.meal_slot)
        known = holidays.sub_holidays(sub)
        owed: list[list[str]] = []
        for day in dates:
            if day in known:
                continue
            rows = db.query(Order).filter(
                Order.subscription_reference_id == sub.subscription_id, Order.order_date == day,
            ).with_for_update().all()
            owed_slots = []
            for meal in rows:
                # a meal the kitchen already started or packed ahead of its date is still owed
                still_owed = meal.status in _AT_KITCHEN or (meal.status == "cancelled" and meal.cancel_reason == "paused")
                if not still_owed:
                    continue  # skipped by the customer, or already handled
                meal.status = "cancelled"
                meal.cancel_reason = REASON
                meal.vendor_holiday_reference_id = h.vendor_holiday_id
                owed_slots.append(meal.meal_slot)
                cancelled_total += 1
                if meal.delivery_boy_reference_id:
                    partners[meal.delivery_boy_reference_id].add(day)
            if not rows:
                owed_slots = list(slots)  # not generated yet: the whole day is owed
            known.add(day)
            if owed_slots:
                owed.append(owed_slots)

        old_end = sub.end_date
        if owed:
            extension = holidays.extend(db, sub.vendor_reference_id, old_end, len(owed), skip=known)
            known |= set(extension.holiday_dates)
            sub.end_date = extension.end
            # a make-up day only carries the meals that were owed on the holiday
            not_owed = []
            for day, owed_slots in zip(extension.meal_dates, owed):
                for slot in slots:
                    if slot not in owed_slots:
                        not_owed.append(_not_owed_row(sub, day, slot))
            for row in not_owed:
                db.add(Order(**row))
        holidays.set_sub_holidays(sub, known)
        db.flush()
        if sub.status == "active":
            meals.generate_meals(db, sub, from_date=old_end)

        touched += 1
        last_meal = sub.end_date - timedelta(days=1)
        shown = ", ".join(d.strftime("%a %d %b") for d in dates[:6]) + (" …" if len(dates) > 6 else "")
        notify.customer(
            db, sub.user_reference_id, "vendor_holiday", "Your kitchen has a holiday coming up",
            f"{kitchen_name} will be closed on {shown}. There is no delivery and no charge for those days. "
            f"Your plan keeps every meal you paid for and now ends on {last_meal.strftime('%d %b %Y')}.",
            {
                "subscription_id": str(sub.subscription_id),
                "vendor_holiday_id": str(h.vendor_holiday_id),
                "dates": [d.isoformat() for d in dates],
                "will_be_delivered": False,
                "new_end_date": sub.end_date.isoformat(),
                "last_meal_date": last_meal.isoformat(),
            },
            dedupe_key=f"casual_holiday:{h.vendor_holiday_id}:{sub.subscription_id}",
        )

    for boy, days in partners.items():
        shown = ", ".join(d.strftime("%a %d %b") for d in sorted(days))
        notify.delivery_partner(
            db, boy, "schedule_update", "Deliveries cancelled - kitchen holiday",
            f"{kitchen_name} is closed on {shown}. Those deliveries are off your schedule.",
            {"vendor_holiday_id": str(h.vendor_holiday_id), "dates": [d.isoformat() for d in sorted(days)]},
        )
    h.affected_subscriptions = (h.affected_subscriptions or 0) + touched
    h.affected_meals = (h.affected_meals or 0) + cancelled_total
    h.processing_status = "completed"
    business_event("holiday.casual_applied", holiday_id=h.vendor_holiday_id, subscriptions=touched,
                   meals=cancelled_total)
    return {"affected_subscriptions": touched, "cancelled_meals": cancelled_total}
