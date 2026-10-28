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

One-time orders already placed for a new holiday date are cancelled and
refunded in full. Every notice goes through the holiday notice log
(app/domain/holiday_notices.py), so it is sent only after the change commits
and a failed one is retried without re-planning anything.

Only approved holidays get here: a kitchen's request is applied when an
admin approves it (app/services/holiday_request_service.py).

Changing or removing an approved regular holiday (2026-10-28) is refused
while it would touch a running subscription: change_conflicts() lists the
running plans with a date that would open or close inside what is left of
them, and assert_no_conflicts() refuses the change (409
HOLIDAY_CHANGE_BLOCKED) - when the kitchen asks, and again when an admin
approves. Adding a holiday is not restricted (it re-plans, as above).
"""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.audit import business_event
from app.core.clock import today_local
from app.core.errors import DomainError
from app.domain import holiday_notices, holidays, orders as meals
from app.domain.pricing import money
from app.domain.slots import expand_plan_slot
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.subscription_model import Subscription
from app.models.vendor_holiday_model import VendorHoliday

RUNNING = ("active", "paused")
EXTRA_OPEN = ("pending", "confirmed", "preparing", "ready_for_pickup")
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


def change_conflicts(db: Session, provider_id, changed) -> dict:
    """
    Running subscriptions (active / paused) of the kitchen that changing or
    removing a regular holiday would touch. `changed(lo, hi)` gives the
    dates in [lo, hi] that would open or close; only what is left of each
    plan counts (from tomorrow to its last day). A regular holiday closes
    the whole day, so every meal of the plan that day is concerned.
    """
    first = today_local() + timedelta(days=1)
    subs = db.query(Subscription).filter(
        Subscription.vendor_reference_id == provider_id,
        Subscription.status.in_(RUNNING),
        Subscription.end_date > first,
    ).all()
    hits: list[tuple[Subscription, set]] = []
    for sub in subs:
        lo, hi = max(first, sub.start_date), sub.end_date - timedelta(days=1)
        dates = set(changed(lo, hi)) if lo <= hi else set()
        if dates:
            hits.append((sub, dates))
    return {
        "affected_subscriptions": len(hits),
        "dates": sorted({d for _, dates in hits for d in dates})[:10],
        # the last day of the latest of those plans: after it they no longer stand in the way
        "clear_after": max(sub.end_date - timedelta(days=1) for sub, _ in hits) if hits else None,
    }


def blocked_message(conflicts: dict, verb: str) -> str:
    """Why a regular holiday cannot be `verb` ('changed', 'removed') now, for the kitchen and the admin."""
    n = conflicts["affected_subscriptions"]
    shown = ", ".join(d.strftime("%a %d %b") for d in conflicts["dates"][:4])
    more = " …" if len(conflicts["dates"]) > 4 else ""
    until = conflicts["clear_after"]
    return (
        f"This holiday cannot be {verb} now: it would change the meal days of {n} running "
        f"subscription{'s' if n != 1 else ''} ({shown}{more}). You can ask again after "
        f"{until.strftime('%d %b %Y')}, when those plans have ended."
    )


def assert_no_conflicts(db: Session, provider_id, changed, verb: str) -> None:
    """409 HOLIDAY_CHANGE_BLOCKED when changing / removing a regular holiday would touch a running subscription."""
    conflicts = change_conflicts(db, provider_id, changed)
    if conflicts["affected_subscriptions"]:
        raise DomainError(
            blocked_message(conflicts, verb), 409, code="HOLIDAY_CHANGE_BLOCKED",
            extra={
                "affected_subscriptions": conflicts["affected_subscriptions"],
                "dates": [d.isoformat() for d in conflicts["dates"]],
                "clear_after": conflicts["clear_after"].isoformat(),
            },
        )


def rule_change(old: VendorHoliday, new: VendorHoliday | None):
    """`changed(lo, hi)` for replacing `old` with `new` (None: removing it): the dates that open or close."""
    if new is None:
        return lambda lo, hi: holidays.rule_dates(old, lo, hi)
    return lambda lo, hi: holidays.rule_dates(old, lo, hi) ^ holidays.rule_dates(new, lo, hi)


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


def _cancel_extra_orders(db: Session, h: VendorHoliday, kitchen_name: str, partners: dict, *, request_id=None) -> int:
    """One-time orders already placed for a new holiday date: cancelled and refunded in full."""
    first = today_local() + timedelta(days=1)
    rows = db.query(ExtraOrder).filter(
        ExtraOrder.vendor_reference_id == h.provider_reference_id,
        ExtraOrder.delivery_date >= max(first, h.start_date),
        ExtraOrder.status.in_(EXTRA_OPEN),
        ExtraOrder.refunded_at.is_(None),
    )
    if h.end_date is not None:
        rows = rows.filter(ExtraOrder.delivery_date <= h.end_date)
    cancelled = 0
    for order in rows.order_by(ExtraOrder.extra_order_id).with_for_update().all():
        if not holidays.rule_dates(h, order.delivery_date, order.delivery_date):
            continue
        order.status = "cancelled"
        order.cancel_reason = REASON
        amount = meals.refund_extra_order(
            db, order, reason="order_cancel_refund",
            description=f"Refund: kitchen holiday on {order.delivery_date} (one-time order)",
        )
        if order.delivery_boy_reference_id:
            partners[order.delivery_boy_reference_id].add(order.delivery_date)
        holiday_notices.queue(
            db, "customer", order.user_reference_id, "order_cancelled", "Order cancelled - kitchen holiday",
            f"{kitchen_name} is closed on {order.delivery_date.strftime('%a %d %b')}, so your one-time order "
            f"was cancelled and ₹{money(amount):.2f} refunded to your wallet.",
            {"extra_order_id": order.extra_order_id, "vendor_holiday_id": h.vendor_holiday_id,
             "wallet_credit": f"{money(amount):.2f}"},
            dedupe_key=f"casual_holiday_extra:{h.vendor_holiday_id}:{order.extra_order_id}",
            request_id=request_id, holiday_id=h.vendor_holiday_id,
        )
        cancelled += 1
    return cancelled


def apply(db: Session, h: VendorHoliday, *, request_id=None) -> dict:
    """Re-plan every running subscription the holiday touches (caller commits)."""
    kitchen = db.query(Provider).filter(Provider.provider_id == h.provider_reference_id).first()
    kitchen_name = (kitchen.business_name if kitchen else None) or "Your kitchen"
    partners: dict = defaultdict(set)
    touched = 0
    cancelled_total = 0
    notified: set = set()
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
            extension = holidays.extend(db, sub.vendor_reference_id, old_end, len(owed), skip=known, slots=slots)
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
        holiday_notices.queue(
            db, "customer", sub.user_reference_id, "vendor_holiday", "Your kitchen has a holiday coming up",
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
            request_id=request_id, holiday_id=h.vendor_holiday_id,
        )
        notified.add(sub.subscription_id)

    extra_cancelled = _cancel_extra_orders(db, h, kitchen_name, partners, request_id=request_id)

    for boy, days in partners.items():
        shown = ", ".join(d.strftime("%a %d %b") for d in sorted(days))
        holiday_notices.queue(
            db, "delivery_boy", boy, "schedule_update", "Deliveries cancelled - kitchen holiday",
            f"{kitchen_name} is closed on {shown}. Those deliveries are off your schedule.",
            {"vendor_holiday_id": str(h.vendor_holiday_id), "dates": [d.isoformat() for d in sorted(days)]},
            dedupe_key=f"casual_holiday_partner:{h.vendor_holiday_id}:{boy}",
            request_id=request_id, holiday_id=h.vendor_holiday_id,
        )
    h.affected_subscriptions = (h.affected_subscriptions or 0) + touched
    h.affected_meals = (h.affected_meals or 0) + cancelled_total
    h.processing_status = "completed"
    business_event("holiday.casual_applied", holiday_id=h.vendor_holiday_id, subscriptions=touched,
                   meals=cancelled_total)
    return {"affected_subscriptions": touched, "cancelled_meals": cancelled_total,
            "cancelled_one_time_orders": extra_cancelled, "notified_subscriptions": sorted(str(n) for n in notified)}
