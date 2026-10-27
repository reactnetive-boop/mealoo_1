"""
Emergency holidays: a kitchen suddenly cannot cook on a coming date.

A kitchen only REQUESTS an emergency holiday (app/services/holiday_request_
service.py), and only for a date after today (business-local); nothing
changes until an admin approves it. A holiday is for the whole day
(meal_slots NULL) or only some of the meals the kitchen serves (meal_slots,
e.g. ['lunch']): only those meals are blocked and the others that day run
as usual. Choosing every meal the kitchen serves is the full day. Approval
declares it here: the blocked meals are closed at once - no new order,
subscription meal, preparation task, pickup or delivery can land on them
(holidays.is_slot_closed; holidays.is_closed for a full day) - and the work
is listed:

    meals          subscription meals of that date and those meals still at
                   the kitchen and not cooked out (scheduled / preparing;
                   ahead of the date also ready_for_pickup), not refunded.
                   Delivered, skipped, cancelled or picked-up meals stay as
                   they are, and the subscription itself is never cancelled
                   or re-priced.
    subscriptions  every active subscription of the kitchen: each gets
                   exactly ONE extra free skip for the holiday, whether or not
                   it had a meal that day. A FULL-DAY holiday grants it only
                   when the kitchen normally serves at least two meals a day
                   (meal_offering.free_skip_eligibility); otherwise the rows
                   are 'not_eligible': no skip, the refunds and the notice
                   stay. Holidays for some meals keep the skip as before.
    one-time       one-time orders for that date and those meals at the
                   kitchen are cancelled and refunded in full.

A plan bought (or resumed) after the approval that has a meal on a blocked
meal of that date gets it cancelled and refunded the same way
(refund_blocked_meal, called by meal generation).

An admin can delete an emergency holiday until the delivery time of its
earliest blocked meal (delete_cutoff; the earliest meal the kitchen serves
for a full-day one): the meals open again for new orders, and everything
already refunded or credited stays with the customers (remove).

Business rule (2026-10-26): no replacement kitchen. Each affected meal is
not deliverable (cancelled, 'vendor_emergency_holiday') and its value goes
back to the wallet (VENDOR_EMERGENCY_HOLIDAY_MEAL_REFUND, idempotency key
meal_refund:<order>, shared with every other refund, so a meal is never
refunded twice). The replacement search below is kept for a later decision
(REPLACEMENT_ENABLED) and is not used.

Every meal, subscription and one-time order is processed in its own
transaction with row locks; the skip credit has its own idempotency key
(holiday_skip:<holiday>:<subscription>) and the per-holiday row is unique,
so retries never credit twice. The customer is told - closure, refunded
amount, wallet balance after it and the extra skip - only after the money
and the skip are committed, through the holiday notice log
(app/domain/holiday_notices.py): a failed notice is retried from the log
without touching money again. The kitchen's delivery partners are told no
pickup is needed that day.
"""

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.audit import business_event, record_audit
from app.core.clock import now_local, now_utc, today_local
from app.core.errors import DomainError
from app.domain import capacity, holiday_notices, holidays, ledger, meal_offering, notify, ratings, vendor_partner
from app.domain import orders as meals
from app.domain.eligibility import (
    kitchen_serves, package_block_reason, parse_pincode, provider_block_reason, serves_pincode_filter,
    serviceable_pincode,
)
from app.domain.meal_offering import SkipEligibility
from app.domain.pricing import ZERO, money, subscription_unit_price
from app.domain.slots import SLOT_WINDOWS, SLOTS, delivery_starts, ordered_slots, package_serves, slots_label
from app.core.clock import local_datetime
from app.models.extra_order_model import ExtraOrder
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.provider_selected_package_model import ProviderSelectedPackage
from app.models.skip_credit_model import SkipCreditTransaction
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.user_address_model import UserAddress
from app.models.vendor_holiday_model import VendorHoliday, VendorHolidayMeal, VendorHolidaySubscription
from app.models.wallet_model import Wallet

logger = logging.getLogger("app.holidays")

SKIP_REASON = "VENDOR_EMERGENCY_HOLIDAY_COMPENSATION"
REFUND_REASON = "VENDOR_EMERGENCY_HOLIDAY_MEAL_REFUND"
CANCEL_REASON = "vendor_emergency_holiday"
# skip rows of a full-day holiday at a kitchen serving fewer than two meals a day
NOT_ELIGIBLE = "not_eligible"
SKIP_DONE = ("completed", NOT_ELIGIBLE)
# meal_slots values meaning "the whole day"
FULL_DAY_TOKENS = {"full_day", "full", "all", "all_day", "all_slots"}
EXTRA_REFUND_REASON = "order_cancel_refund"
AFFECTED_STATUSES = ("scheduled", "preparing")
# Kitchens may mark meals ready ahead of their date; such a meal is still at the
# closed kitchen, so on a later date it is affected too. Today a packed meal
# (ready for pickup) is delivered as normal.
AHEAD_AFFECTED_STATUSES = AFFECTED_STATUSES + ("ready_for_pickup",)
EXTRA_AFFECTED_STATUSES = ("pending", "confirmed", "preparing")
# Business rule 2026-10-26: an approved emergency refunds the day's meals; no
# replacement kitchen is looked for. The search is kept for a later decision.
REPLACEMENT_ENABLED = False
# Subscriptions that get the extra free skip
SKIP_STATUSES = ("active",)
# Subscriptions whose meals of the day are refunded
MEAL_STATUSES = ("active", "paused")


def _affected_statuses(on: date) -> tuple[str, ...]:
    return AHEAD_AFFECTED_STATUSES if on > today_local() else AFFECTED_STATUSES


def _extra_statuses(on: date) -> tuple[str, ...]:
    return EXTRA_AFFECTED_STATUSES + ("ready_for_pickup",) if on > today_local() else EXTRA_AFFECTED_STATUSES


MAX_DAYS_AHEAD = 30
MAX_ATTEMPTS = 5

# {when}: "today" (the usual case, word for word as agreed) or "on 06 Oct 2026"
REPLACED_MESSAGE = (
    "Sorry for the inconvenience! Your regular vendor is unavailable {when} due to an emergency. "
    "We have arranged your meal from {vendor} at no extra cost. Your meal will be delivered as scheduled."
)
LEAVE_TITLE = "Your kitchen is on leave {when}"
LEAVE_MESSAGE = (
    "{kitchen} is on leave {when} due to an emergency, so food service will not be available that day."
)
# a holiday for some meals only: {meals} = "lunch", "breakfast and dinner"
MEALS_TITLE = "No {meals} from your kitchen {when}"
MEALS_MESSAGE = (
    "{kitchen} cannot serve {meals} {when} due to an emergency, so {meals} will not be available that day. "
    "Other meals that day are not affected."
)
REOPEN_TITLE = "Your kitchen is open again {when}"
REOPEN_MESSAGE = (
    "Good news: Orleeno cancelled the emergency holiday of {kitchen} {when}, so {meals} can be ordered again. "
    "Refunds and the extra free skip already given stay with you; meals already cancelled for that day stay "
    "cancelled."
)
REFUND_MESSAGE = (
    " We've refunded ₹{amount} for {meals} to your wallet. Your wallet balance is now ₹{balance}."
)
NOTHING_DUE_MESSAGE = " You had no meal due from them that day, so nothing was charged."
SKIP_MESSAGE = (
    " As a thank-you for your patience, we've added 1 extra free meal skip to your plan - use it like any "
    "other free skip. Sorry for the inconvenience."
)


# ── Food compatibility ────────────────────────────────────────

def dietary_class(food_type: str | None) -> str:
    """veg | egg | non_veg: what a customer's meal must stay within."""
    tokens = {t.strip().lower().replace("-", "_").replace(" ", "_") for t in (food_type or "").split(",")}
    if tokens & {"non_veg", "nonveg", "non_vegetarian"}:
        return "non_veg"
    if "egg" in tokens:
        return "egg"
    return "veg"


def _when(on: date) -> tuple[str, str]:
    """("today", "today's meal") or ("on 06 Oct 2026", "your meal on 06 Oct 2026")."""
    if on == today_local():
        return "today", "today's meal"
    day = on.strftime("%d %b %Y")
    return f"on {day}", f"your meal on {day}"


def _fmt(on: date) -> str:
    return on.strftime("%d %b %Y")


def _meals(slots) -> str:
    """'lunch', 'breakfast and dinner' (for sentences)."""
    return slots_label(slots).lower()


def leave_notice(kitchen: str, on: date, slots) -> tuple[str, str]:
    """(title, body) telling a customer what the holiday blocks: the whole day, or the named meals."""
    when, _ = _when(on)
    if not slots:
        return LEAVE_TITLE.format(when=when), LEAVE_MESSAGE.format(kitchen=kitchen, when=when)
    return (MEALS_TITLE.format(meals=_meals(slots), when=when),
            MEALS_MESSAGE.format(kitchen=kitchen, meals=_meals(slots), when=when))


# ── Rules of a request ────────────────────────────────────────

def validate_future(on: date) -> None:
    """A kitchen may only ask for an emergency holiday after today (business-local date)."""
    today = today_local()
    if on <= today:
        state = "today" if on == today else "in the past"
        raise DomainError(f"Emergency holidays can only be created for future dates. {_fmt(on)} is {state}.",
                          422, code="HOLIDAY_NOT_FUTURE")


def normalize_slots(db: Session, provider_id, on: date, meal_slots) -> list[str] | None:
    """
    The meals an emergency holiday blocks, validated (DomainError 422):
    None = the whole day (nothing sent, a 'full_day' option, or every meal
    the kitchen serves). At least one meal; only meals the kitchen serves.
    """
    if meal_slots is None:
        return None
    if isinstance(meal_slots, str):
        meal_slots = meal_slots.split(",")
    tokens = [str(s).strip().lower().replace(" ", "_").replace("-", "_") for s in meal_slots]
    tokens = [t for t in tokens if t]
    if not tokens:
        raise DomainError("Choose at least one meal to block (Breakfast, Lunch or Dinner), or the full day.",
                          422, code="HOLIDAY_MEALS_REQUIRED")
    if any(t in FULL_DAY_TOKENS for t in tokens):
        return None
    unknown = [t for t in tokens if t not in SLOTS]
    if unknown:
        raise DomainError(f"Unknown meal '{unknown[0]}'. Choose from Breakfast, Lunch and Dinner.", 422,
                          code="HOLIDAY_SLOT_UNKNOWN")
    chosen = ordered_slots(tokens)
    offered = meal_offering.offered_slots(db, provider_id, on)
    missing = [s for s in chosen if s not in offered]
    if missing:
        raise DomainError(
            f"Your kitchen does not serve {slots_label(missing)}, so it cannot be blocked. "
            f"Meals you serve: {slots_label(offered) or 'none'}.",
            422, code="HOLIDAY_SLOT_NOT_OFFERED",
        )
    if set(offered) <= set(chosen):
        return None  # every meal the kitchen serves: the full day
    return chosen


def skip_decision(db: Session, provider_id, on: date, slots) -> SkipEligibility:
    """Whether the holiday grants the extra free skip: holidays for some meals always do (unchanged)."""
    if slots:
        return SkipEligibility(True, tuple(slots), "a holiday for some meals keeps the free skip")
    return meal_offering.free_skip_eligibility(db, provider_id, on)


def delete_cutoff(db: Session, holiday: VendorHoliday) -> datetime:
    """
    Until when an admin may delete the emergency holiday (business-local,
    tz-aware): the delivery time - start of the delivery window - of its
    earliest blocked meal; for a full-day holiday the earliest meal the
    kitchen serves that day (breakfast when it lists none).
    """
    slots = (holiday.meal_slots
             or meal_offering.offered_slots(db, holiday.provider_reference_id, holiday.start_date)
             or SLOTS)
    return delivery_starts(holiday.start_date, ordered_slots(slots)[0])


# ── Step 1: affected meals ────────────────────────────────────

def affected_orders(db: Session, provider_id, on: date, slots=None) -> list[Order]:
    """Subscription meals the holiday takes away: that date, and only the blocked meals when `slots` is given."""
    q = (
        db.query(Order)
        .join(Subscription, Subscription.subscription_id == Order.subscription_reference_id)
        .filter(
            Order.vendor_reference_id == provider_id,
            Order.order_date == on,
            Order.status.in_(_affected_statuses(on)),
            Order.refunded_at.is_(None),
            # a paused plan can still owe the meal of a day before its pause starts
            Subscription.status.in_(MEAL_STATUSES),
        )
    )
    if slots:
        q = q.filter(Order.meal_slot.in_(list(slots)))
    return q.order_by(Order.order_id).all()


def skip_subscriptions(db: Session, provider_id) -> list[Subscription]:
    """Every active subscription of the kitchen still running: each gets one extra free skip."""
    return (
        db.query(Subscription)
        .filter(
            Subscription.vendor_reference_id == provider_id,
            Subscription.status.in_(SKIP_STATUSES),
            Subscription.end_date > today_local(),
        )
        .order_by(Subscription.subscription_id)
        .all()
    )


def affected_extra_orders(db: Session, provider_id, on: date, slots=None) -> list[ExtraOrder]:
    q = db.query(ExtraOrder).filter(
        ExtraOrder.vendor_reference_id == provider_id,
        ExtraOrder.delivery_date == on,
        ExtraOrder.status.in_(_extra_statuses(on)),
        ExtraOrder.refunded_at.is_(None),
    )
    if slots:
        q = q.filter(ExtraOrder.meal_slot.in_(list(slots)))
    return q.order_by(ExtraOrder.extra_order_id).all()


def preview(db: Session, provider_id, on: date, slots=None) -> dict:
    """What approving an emergency holiday for `on` (the whole day, or `slots`) would do (nothing is saved)."""
    orders = affected_orders(db, provider_id, on, slots)
    extras = affected_extra_orders(db, provider_id, on, slots)
    skip = skip_decision(db, provider_id, on, slots)
    by_slot: dict = {}
    refund = ZERO
    subs: dict = {}
    for o in orders:
        by_slot[o.meal_slot] = by_slot.get(o.meal_slot, 0) + 1
        sub = subs.get(o.subscription_reference_id) or db.get(Subscription, o.subscription_reference_id)
        subs[o.subscription_reference_id] = sub
        refund += meals.meal_value(sub) if sub is not None else ZERO
    refund += sum((money(e.total_price) for e in extras), ZERO)
    return {
        "date": on,
        # the meals asked for; None = the whole day
        "meal_slots": slots or None,
        "full_day": not slots,
        "affected_orders": len(orders),
        "affected_subscriptions": len(subs),
        "by_meal_slot": by_slot,
        "one_time_orders": len(extras),
        # every active subscription of the kitchen gets one extra free skip (when the holiday grants it)
        "skip_credits": len(skip_subscriptions(db, provider_id)) if skip.eligible else 0,
        "free_skip": skip.view(),
        "estimated_refund": str(money(refund)),
    }


def _validate_date(on: date) -> None:
    today = today_local()
    if on < today:
        raise DomainError("An emergency holiday cannot be declared for a past date", code="HOLIDAY_IN_PAST")
    if on > today + timedelta(days=MAX_DAYS_AHEAD):
        raise DomainError(f"An emergency holiday can be declared at most {MAX_DAYS_AHEAD} days ahead. "
                          "Plan longer closures as holidays.")


def validate_request(db: Session, provider_id, on: date, slots=None, *, future_only: bool = False) -> None:
    """
    Checks an emergency holiday for `on` and `slots` (None = the whole day;
    raises DomainError): the date (after today for a kitchen's request),
    and no approved holiday already closing that day or one of those meals.
    """
    if future_only:
        validate_future(on)
    _validate_date(on)
    wanted = set(slots or SLOTS)
    for existing in holidays.holidays_on(db, provider_id, on):
        if existing.holiday_type != holidays.EMERGENCY:
            raise DomainError(f"{on} is already a holiday: no meals are scheduled that day", 409,
                              code="HOLIDAY_EXISTS")
        overlap = wanted & set(holidays.holiday_slots(existing))
        if not overlap:
            continue
        if holidays.is_full_day(existing) and not slots:
            raise DomainError(f"An emergency holiday is already approved for {on}", 409, code="HOLIDAY_EXISTS")
        raise DomainError(f"An emergency holiday is already approved for {slots_label(overlap)} on {_fmt(on)}",
                          409, code="HOLIDAY_EXISTS")


def declare(db: Session, provider_id, on: date, reason: str | None, *, actor_type: str, actor_id,
            commit: bool = True, request_id=None, meal_slots=None) -> VendorHoliday:
    """
    Close the kitchen for `on` - the whole day, or only `meal_slots` - and
    list the work (meals to refund, subscriptions for the skip, partners to
    tell). Runs when an admin approves a kitchen's request or declares one;
    process() then does the work.
    """
    _validate_date(on)
    slots = ordered_slots(meal_slots) or None
    # one declaration at a time per kitchen
    kitchen = db.query(Provider).filter(Provider.provider_id == provider_id).with_for_update().first()
    if kitchen is None:
        raise DomainError("Kitchen not found", 404)
    validate_request(db, provider_id, on, slots)

    holiday = VendorHoliday(
        vendor_holiday_id=uuid.uuid4(), provider_reference_id=provider_id, holiday_type=holidays.EMERGENCY,
        rule_type="dates", dates=[on], start_date=on, end_date=on, meal_slots=slots,
        reason=(reason or "").strip() or None, status="active", processing_status="pending",
        created_by_type=actor_type, created_by=actor_id,
    )
    db.add(holiday)
    db.flush()
    orders = affected_orders(db, provider_id, on, slots)
    if orders:
        db.execute(
            pg_insert(VendorHolidayMeal).values([
                {
                    "vendor_holiday_meal_id": uuid.uuid4(),
                    "vendor_holiday_reference_id": holiday.vendor_holiday_id,
                    "order_reference_id": o.order_id,
                    "subscription_reference_id": o.subscription_reference_id,
                    "user_reference_id": o.user_reference_id,
                    "original_vendor_reference_id": o.vendor_reference_id,
                    "meal_date": o.order_date,
                    "meal_slot": o.meal_slot,
                }
                for o in orders
            ]).on_conflict_do_nothing(constraint="uq_vendor_holiday_meal")
        )
    subs = skip_subscriptions(db, provider_id)
    skip = skip_decision(db, provider_id, on, slots)
    if not skip.eligible:
        _log_no_skip(holiday, skip, subscriptions=len(subs))
    if subs:
        db.execute(
            pg_insert(VendorHolidaySubscription).values([
                {
                    "vendor_holiday_subscription_id": uuid.uuid4(),
                    "vendor_holiday_reference_id": holiday.vendor_holiday_id,
                    "subscription_reference_id": sub.subscription_id,
                    "user_reference_id": sub.user_reference_id,
                    "skip_status": "pending" if skip.eligible else NOT_ELIGIBLE,
                    "attempts": 0,
                    "refunded_meals": 0,
                    "refund_amount": ZERO,
                }
                for sub in subs
            ]).on_conflict_do_nothing(constraint="uq_vendor_holiday_subscription")
        )
    holiday.affected_meals = len(orders)
    holiday.affected_subscriptions = len({o.subscription_reference_id for o in orders})
    _queue_partner_notices(db, holiday, kitchen, request_id=request_id)
    record_audit(
        db, table="provider.vendor_holidays", record_id=holiday.vendor_holiday_id, operation="I",
        new={"type": "emergency", "date": on, "meal_slots": slots, "reason": holiday.reason,
             "affected_meals": len(orders), "skip_credits": len(subs) if skip.eligible else 0,
             "free_skip": skip.view(), "request_id": str(request_id) if request_id else None},
        actor_id=actor_id, actor_type=actor_type,
    )
    business_event("holiday.emergency_declared", provider_id=provider_id, date=on, meal_slots=slots,
                   meals=len(orders), subscriptions=len(subs), free_skip=skip.eligible)
    if commit:
        db.commit()
    return holiday


def _log_no_skip(holiday: VendorHoliday, skip: SkipEligibility, *, subscriptions: int) -> None:
    """Every full-day holiday that grants no free skip says why, in the log and as a business event."""
    logger.info("no free skip for emergency holiday %s (kitchen %s, %s): %s", holiday.vendor_holiday_id,
                holiday.provider_reference_id, holiday.start_date, skip.reason)
    business_event("holiday.free_skip_not_granted", holiday_id=holiday.vendor_holiday_id,
                   provider_id=holiday.provider_reference_id, date=holiday.start_date, reason=skip.reason,
                   meals_per_day=len(skip.slots), subscriptions=subscriptions)


def _new_skip_status(db: Session, holiday: VendorHoliday) -> str:
    """skip_status of a subscription row added after the declaration (a paused plan with a meal that day)."""
    skip = skip_decision(db, holiday.provider_reference_id, holiday.start_date, holiday.meal_slots)
    if not skip.eligible:
        _log_no_skip(holiday, skip, subscriptions=1)
    return "pending" if skip.eligible else NOT_ELIGIBLE


def _partners(db: Session, kitchen_id, on: date, slots) -> set:
    """The kitchen's partner and every partner holding its meals of `on` (of `slots` when given)."""
    partners = set()
    row = vendor_partner.kitchen_row(db, kitchen_id)
    if row is not None:
        partners.add(row.delivery_boy_reference_id)
    subs = db.query(Order.delivery_boy_reference_id).filter(
        Order.vendor_reference_id == kitchen_id, Order.order_date == on, Order.delivery_boy_reference_id.isnot(None),
    )
    extras = db.query(ExtraOrder.delivery_boy_reference_id).filter(
        ExtraOrder.vendor_reference_id == kitchen_id, ExtraOrder.delivery_date == on,
        ExtraOrder.delivery_boy_reference_id.isnot(None),
    )
    if slots:
        subs = subs.filter(Order.meal_slot.in_(list(slots)))
        extras = extras.filter(ExtraOrder.meal_slot.in_(list(slots)))
    partners |= {boy for (boy,) in subs.distinct()} | {boy for (boy,) in extras.distinct()}
    return {p for p in partners if p is not None}


def _queue_partner_notices(db: Session, holiday: VendorHoliday, kitchen: Provider, *, request_id=None) -> None:
    """The kitchen's partners: no pickup there that day / for those meals (meals already packed or picked up stay theirs)."""
    on, slots = holiday.start_date, holiday.meal_slots
    name = kitchen.business_name or "Your kitchen"
    when, _ = _when(on)
    for boy in sorted(_partners(db, kitchen.provider_id, on, slots), key=str):
        on_route = db.query(Order.order_id).filter(
            Order.vendor_reference_id == kitchen.provider_id, Order.order_date == on,
            Order.delivery_boy_reference_id == boy,
            Order.status.in_(("ready_for_pickup", "picked_up", "out_for_delivery")),
            *((Order.meal_slot.in_(list(slots)),) if slots else ()),
        ).count()
        if slots:
            title = f"{name}: no {_meals(slots)} {when}"
            body = (f"{name} cannot serve {_meals(slots)} {when}. No {_meals(slots)} pickup is required from this "
                    "kitchen that day; its other meals are picked up as usual.")
        else:
            title = f"{name} is on leave {when}"
            body = f"{name} is on leave {when}. No pickup is required from this kitchen that day."
        if on_route:
            body += f" {on_route} meal(s) already packed or picked up stay on your list."
        holiday_notices.queue(
            db, "delivery_boy", boy, "schedule_update", title, body,
            {"vendor_holiday_id": holiday.vendor_holiday_id, "provider_id": kitchen.provider_id,
             "date": on.isoformat(), "pickup_required": False, "meal_slots": slots},
            dedupe_key=f"holiday_pickup:{holiday.vendor_holiday_id}:{boy}",
            request_id=request_id, holiday_id=holiday.vendor_holiday_id,
        )


# ── Step 2: replacement kitchen ───────────────────────────────

def _slot_still_deliverable(on: date, slot: str) -> bool:
    """A replacement kitchen must be able to start before the meal's delivery window opens."""
    window = SLOT_WINDOWS.get(slot)
    if window is None:
        return False
    return now_local() < local_datetime(on, window[0])


def _spare(db: Session, provider_id, package_id, slot: str, on: date, quantity: int) -> int | None:
    """Room left for `quantity` more meals, or None when it does not fit (package and kitchen limits)."""
    spare = []
    cap = capacity.package_capacity(db, provider_id, package_id)
    if cap is not None:
        used = capacity.committed(db, provider_id, slot, on, on, package_id).get(on, 0)
        spare.append(cap - used)
    quota = capacity.kitchen_quota(db, provider_id)
    if quota is not None:
        used = capacity.committed(db, provider_id, slot, on, on).get(on, 0)
        spare.append(quota - used)
    room = min(spare) if spare else 10_000
    return room - quantity if room >= quantity else None


def _required(db: Session, order: Order, sub: Subscription):
    """(package to match, per-unit price ceiling, quantity) of the customer's meal."""
    sub_pkg = db.query(SubscriptionPackage).filter(
        SubscriptionPackage.subscription_reference_id == sub.subscription_id
    ).first()
    package_id = order.replacement_package_reference_id or (sub_pkg.package_reference_id if sub_pkg else None)
    package = db.query(MenuPackage).filter(MenuPackage.package_id == package_id).first() if package_id else None
    snapshot = sub.pricing_snapshot or {}
    if snapshot.get("base_unit_price") is not None:
        ceiling = money(snapshot["base_unit_price"])
    else:
        ceiling = money(sub_pkg.unit_price if sub_pkg else 0)
    return package, ceiling, (sub_pkg.quantity if sub_pkg else 1)


def candidates(db: Session, order: Order, sub: Subscription, *, exclude=()) -> tuple[list[dict], list[dict]]:
    """
    (eligible, rejected) replacement offers for one meal, eligible sorted by
    the deterministic preference. Every offer within reach is evaluated so
    the rejection reasons can be audited.
    """
    package, ceiling, quantity = _required(db, order, sub)
    address = db.query(UserAddress).filter(UserAddress.user_address_id == order.delivery_address_reference_id).first()
    pin = parse_pincode(address.pin_code) if address else None
    if package is None or pin is None:
        return [], [{"reason": "the meal has no package or delivery PIN code"}]
    diet = dietary_class(package.food_type)
    on, slot = order.order_date, order.meal_slot
    blocked = {order.vendor_reference_id, *exclude}

    rows = (
        db.query(Provider, MenuPackage)
        .join(ProviderSelectedPackage, ProviderSelectedPackage.provider_id == Provider.provider_id)
        .join(MenuPackage, MenuPackage.package_id == ProviderSelectedPackage.package_id)
        .filter(
            ProviderSelectedPackage.is_active == True,  # noqa: E712
            Provider.provider_id.notin_(list(blocked)),
            # kitchens that cannot reach the customer are never candidates
            serves_pincode_filter(pin),
        )
        .order_by(Provider.provider_id, MenuPackage.package_id)
        .all()
    )
    closed = holidays.kitchens_closed_for(db, {p.provider_id for p, _ in rows}, on, slot)
    stats = ratings.for_offers(db, [(m.package_id, p.provider_id) for p, m in rows])
    deliverable = _slot_still_deliverable(on, slot)

    eligible, rejected = [], []
    for kitchen, offer in rows:
        why = provider_block_reason(kitchen) or package_block_reason(offer)
        price = subscription_unit_price(offer)
        if why:
            pass
        elif serviceable_pincode(db, kitchen.pincode) is None:
            why = "kitchen area not serviced"
        elif not kitchen_serves(db, kitchen, pin):
            why = "does not deliver to the customer's PIN code"
        elif kitchen.provider_id in closed:
            why = "kitchen is on holiday that day"
        elif not package_serves(offer.meal_type, [slot]):
            why = f"package is not served for {slot}"
        elif dietary_class(offer.food_type) != diet:
            why = f"dietary type does not match ({diet})"
        elif price > ceiling:
            why = f"price {price} is higher than the subscribed {ceiling}"
        elif not deliverable:
            why = "cannot reach the delivery time slot any more"
        spare = None
        if why is None:
            spare = _spare(db, kitchen.provider_id, offer.package_id, slot, on, quantity)
            if spare is None:
                why = "no capacity left for that meal"
        if why:
            rejected.append({"provider_id": str(kitchen.provider_id), "package_id": str(offer.package_id),
                             "reason": why})
            continue
        if offer.package_id == package.package_id:
            compat = 0
        elif offer.category_reference_id == package.category_reference_id:
            compat = 1
        else:
            compat = 2
        rating = ratings.get(stats, offer.package_id, kitchen.provider_id)["rating_average"] or 0
        eligible.append({
            "provider": kitchen, "package": offer, "unit_price": price, "quantity": quantity, "ceiling": ceiling,
            "rank": (compat, -rating, -spare, 0 if kitchen.pincode == pin else 1,
                     str(kitchen.provider_id), str(offer.package_id)),
        })
    eligible.sort(key=lambda c: c["rank"])
    return eligible, rejected


# ── One meal ──────────────────────────────────────────────────

def _vh_sub(db: Session, holiday_id, subscription_id) -> VendorHolidaySubscription | None:
    return db.query(VendorHolidaySubscription).filter(
        VendorHolidaySubscription.vendor_holiday_reference_id == holiday_id,
        VendorHolidaySubscription.subscription_reference_id == subscription_id,
    ).with_for_update().populate_existing().first()


def process_meal(db: Session, record_id) -> str:
    """
    Process one affected meal exactly once (commits). Returns the outcome.
    Lock order: holiday-meal record -> subscription -> meal -> holiday subscription row.
    """
    rec = db.query(VendorHolidayMeal).filter(
        VendorHolidayMeal.vendor_holiday_meal_id == record_id
    ).with_for_update().populate_existing().one()
    if rec.processing_status == "completed":
        db.rollback()
        return rec.outcome
    holiday = db.query(VendorHoliday).filter(VendorHoliday.vendor_holiday_id == rec.vendor_holiday_reference_id).one()
    sub = db.query(Subscription).filter(
        Subscription.subscription_id == rec.subscription_reference_id
    ).with_for_update().populate_existing().one()
    order = db.query(Order).filter(Order.order_id == rec.order_reference_id).with_for_update().populate_existing().one()
    rec.attempts = (rec.attempts or 0) + 1

    still_affected = (
        order.status in _affected_statuses(order.order_date) and order.refunded_at is None
        and sub.status in MEAL_STATUSES
        and str(order.vendor_reference_id) == str(rec.original_vendor_reference_id)
    )
    if not still_affected:
        # delivered / skipped / cancelled / moved before we got to it: nothing owed
        rec.outcome = "not_affected"
        rec.processing_status = "completed"
        rec.notification_status = "not_required"
        rec.processed_at = now_utc()
        db.commit()
        return rec.outcome

    chosen, rejected = None, []
    if REPLACEMENT_ENABLED:
        eligible, rejected = candidates(db, order, sub)
        for option in eligible:
            # lock the replacement kitchen and re-check its room: concurrent meals must not overfill it
            db.query(Provider).filter(Provider.provider_id == option["provider"].provider_id).with_for_update().first()
            if _spare(db, option["provider"].provider_id, option["package"].package_id, order.meal_slot,
                      order.order_date, option["quantity"]) is not None:
                chosen = option
                break

    if chosen is not None:
        kitchen, package = chosen["provider"], chosen["package"]
        sub_pkg_id = db.query(SubscriptionPackage.package_reference_id).filter(
            SubscriptionPackage.subscription_reference_id == sub.subscription_id
        ).scalar()
        old_partner = order.delivery_boy_reference_id
        order.original_vendor_reference_id = order.original_vendor_reference_id or order.vendor_reference_id
        order.vendor_reference_id = kitchen.provider_id
        order.replacement_package_reference_id = None if package.package_id == sub_pkg_id else package.package_id
        order.vendor_holiday_reference_id = holiday.vendor_holiday_id
        order.status = "scheduled"  # the replacement kitchen starts it from scratch
        order.pickup_code_attempts = 0
        order.delivery_boy_reference_id = None
        vendor_partner.assign_moved_order(db, order, "subscription")
        if old_partner and old_partner != order.delivery_boy_reference_id:
            notify.delivery_partner(
                db, old_partner, "schedule_update", "Pickup kitchen changed",
                f"The {order.meal_slot} on {order.order_date} now comes from another kitchen and is no longer yours.",
                {"order_id": str(order.order_id), "kind": "subscription"},
            )
        notify.kitchen(
            db, kitchen.provider_id, "new_order", "Replacement meal to prepare",
            f"Please prepare {package.package_name} x {chosen['quantity']} for {order.meal_slot} on "
            f"{order.order_date}. Another kitchen is closed and Orleeno moved this meal to you.",
            {"order_id": str(order.order_id), "kind": "subscription", "meal_slot": order.meal_slot,
             "meal_date": order.order_date.isoformat(), "package_name": package.package_name},
            dedupe_key=f"replacement_meal:{order.order_id}:{holiday.vendor_holiday_id}",
        )
        rec.outcome = "replaced"
        rec.replacement_vendor_reference_id = kitchen.provider_id
        rec.replacement_package_reference_id = package.package_id
        rec.original_meal_price = money(chosen["ceiling"] * chosen["quantity"])
        rec.replacement_meal_price = money(chosen["unit_price"] * chosen["quantity"])
        rec.compensation_status = "not_required"
        rec.notification_status = "pending"
    else:
        # not deliverable: the meal's value goes back to the wallet, once
        order.status = "cancelled"
        order.cancel_reason = CANCEL_REASON
        order.vendor_holiday_reference_id = holiday.vendor_holiday_id
        amount = meals.refund_meal(
            db, order, sub, reason=REFUND_REASON,
            description=f"Meal refund: kitchen emergency holiday on {order.order_date} ({order.meal_slot})",
        )
        txn = ledger.customer_txn_exists(db, f"meal_refund:{order.order_id}")
        rec.outcome = "compensated"
        rec.meal_amount = money(amount if amount > ZERO else (order.refund_amount or ZERO))
        rec.wallet_transaction_reference_id = txn.wallet_transaction_id if txn else None
        rec.compensation_status = "completed"
        # the customer hears about it once per subscription (process_subscription)
        rec.notification_status = "not_required"
        rec.last_error = "; ".join(sorted({r["reason"] for r in rejected}))[:1000] or None
        row = _vh_sub(db, holiday.vendor_holiday_id, sub.subscription_id)
        if row is None:
            row = VendorHolidaySubscription(
                vendor_holiday_subscription_id=uuid.uuid4(), vendor_holiday_reference_id=holiday.vendor_holiday_id,
                subscription_reference_id=sub.subscription_id, user_reference_id=sub.user_reference_id,
                skip_status=_new_skip_status(db, holiday), attempts=0, refunded_meals=0, refund_amount=ZERO,
            )
            db.add(row)
        row.refunded_meals = (row.refunded_meals or 0) + 1
        row.refund_amount = money(row.refund_amount or ZERO) + rec.meal_amount
    rec.processing_status = "completed"
    rec.processed_at = now_utc()
    db.commit()
    business_event("holiday.meal_processed", holiday_id=holiday.vendor_holiday_id, order_id=order.order_id,
                   outcome=rec.outcome)
    return rec.outcome


# ── One subscription: the extra skip and the customer's notice ─

def _grant_skip(db: Session, sub: Subscription, holiday: VendorHoliday) -> SkipCreditTransaction:
    """Exactly one extra free skip per holiday and subscription (unique idempotency key)."""
    key = f"holiday_skip:{holiday.vendor_holiday_id}:{sub.subscription_id}"
    existing = db.query(SkipCreditTransaction).filter(SkipCreditTransaction.idempotency_key == key).first()
    if existing is not None:
        return existing
    before = (sub.free_skips_total or 0) - (sub.free_skips_used or 0)
    sub.free_skips_total = (sub.free_skips_total or 0) + 1
    txn = SkipCreditTransaction(
        subscription_reference_id=sub.subscription_id, user_reference_id=sub.user_reference_id,
        vendor_reference_id=holiday.provider_reference_id, meal_date=holiday.start_date, type="credit", skips=1,
        reason=SKIP_REASON, free_skips_before=before, free_skips_after=before + 1,
        reference_type="vendor_holiday", reference_id=holiday.vendor_holiday_id,
        description=f"1 extra free skip: kitchen emergency holiday on {holiday.start_date}",
        idempotency_key=key,
    )
    db.add(txn)
    db.flush()
    return txn


def _meals_text(n: int) -> str:
    return "1 meal" if n == 1 else f"{n} meals"


def process_subscription(db: Session, row_id) -> str:
    """
    Grant the subscription's extra skip (once; never for a 'not_eligible'
    row) and, when every meal of it is processed, log the customer's notice
    in the same transaction (commits).
    Lock order: holiday subscription row -> subscription.
    """
    row = db.query(VendorHolidaySubscription).filter(
        VendorHolidaySubscription.vendor_holiday_subscription_id == row_id
    ).with_for_update().populate_existing().one()
    if row.skip_status in SKIP_DONE and row.notice_queued_at is not None:
        db.rollback()
        return "done"
    holiday = db.query(VendorHoliday).filter(VendorHoliday.vendor_holiday_id == row.vendor_holiday_reference_id).one()
    sub = db.query(Subscription).filter(
        Subscription.subscription_id == row.subscription_reference_id
    ).with_for_update().populate_existing().one()
    row.attempts = (row.attempts or 0) + 1
    if row.skip_status not in SKIP_DONE:
        skip = _grant_skip(db, sub, holiday)
        row.skip_credit_reference_id = skip.skip_credit_transaction_id
        row.skip_status = "completed"
        row.processed_at = now_utc()

    unfinished = db.query(VendorHolidayMeal.vendor_holiday_meal_id).filter(
        VendorHolidayMeal.vendor_holiday_reference_id == holiday.vendor_holiday_id,
        VendorHolidayMeal.subscription_reference_id == sub.subscription_id,
        VendorHolidayMeal.processing_status != "completed",
    ).count()
    if unfinished:
        db.commit()  # the skip is booked; the notice waits for the meals' refunds
        return "waiting"

    kitchen = db.query(Provider).filter(Provider.provider_id == holiday.provider_reference_id).first()
    name = (kitchen.business_name if kitchen else None) or "Your kitchen"
    when, _ = _when(holiday.start_date)
    refunded = money(row.refund_amount or ZERO)
    balance = money(db.query(Wallet.balance).filter(Wallet.user_reference_id == sub.user_reference_id).scalar() or ZERO)
    replaced = db.query(VendorHolidayMeal.vendor_holiday_meal_id).filter(
        VendorHolidayMeal.vendor_holiday_reference_id == holiday.vendor_holiday_id,
        VendorHolidayMeal.subscription_reference_id == sub.subscription_id,
        VendorHolidayMeal.outcome == "replaced",
    ).count()
    title, body = leave_notice(name, holiday.start_date, holiday.meal_slots)
    if replaced and not row.refunded_meals:
        # only with the replacement search switched on: the meal still comes, from another kitchen
        body = f"{name} is on leave {when}. Your meal comes from another kitchen at no extra cost."
    elif row.refunded_meals:
        body += REFUND_MESSAGE.format(amount=f"{refunded:.2f}", meals=_meals_text(row.refunded_meals),
                                      balance=f"{balance:.2f}")
    else:
        body += NOTHING_DUE_MESSAGE
    skipped = row.skip_status != NOT_ELIGIBLE
    if skipped:
        body += SKIP_MESSAGE
    free_left = (sub.free_skips_total or 0) - (sub.free_skips_used or 0)
    holiday_notices.queue(
        db, "customer", sub.user_reference_id, "vendor_holiday_compensation", title, body,
        {
            "subscription_id": sub.subscription_id, "vendor_holiday_id": holiday.vendor_holiday_id,
            "provider_id": holiday.provider_reference_id, "meal_date": holiday.start_date.isoformat(),
            "meal_slots": holiday.meal_slots, "full_day": not holiday.meal_slots,
            "will_be_delivered": False, "replacement_vendor_name": None,
            "refunded_meals": row.refunded_meals, "wallet_credit": f"{refunded:.2f}",
            "wallet_balance": f"{balance:.2f}", "skips_credited": 1 if skipped else 0, "free_skips_left": free_left,
        },
        dedupe_key=f"holiday_customer:{holiday.vendor_holiday_id}:{sub.subscription_id}",
        holiday_id=holiday.vendor_holiday_id,
    )
    row.notice_queued_at = now_utc()
    db.commit()
    return "notified"


# ── One-time orders for the date ──────────────────────────────

def cancel_extra_order(db: Session, holiday_id, extra_order_id) -> str:
    """Cancel and refund one one-time order of the closed date (commits); a repeat changes nothing."""
    holiday = db.query(VendorHoliday).filter(VendorHoliday.vendor_holiday_id == holiday_id).one()
    order = db.query(ExtraOrder).filter(
        ExtraOrder.extra_order_id == extra_order_id
    ).with_for_update().populate_existing().one()
    if order.status not in _extra_statuses(order.delivery_date) or order.refunded_at is not None:
        db.rollback()
        return "not_affected"
    order.status = "cancelled"
    order.cancel_reason = CANCEL_REASON
    amount = meals.refund_extra_order(
        db, order, reason=EXTRA_REFUND_REASON,
        description=f"Refund: kitchen emergency holiday on {order.delivery_date} (one-time order)",
    )
    kitchen = db.query(Provider).filter(Provider.provider_id == holiday.provider_reference_id).first()
    name = (kitchen.business_name if kitchen else None) or "Your kitchen"
    _, text = leave_notice(name, holiday.start_date, holiday.meal_slots)
    balance = money(db.query(Wallet.balance).filter(Wallet.user_reference_id == order.user_reference_id).scalar() or ZERO)
    holiday_notices.queue(
        db, "customer", order.user_reference_id, "order_cancelled", "Order cancelled - kitchen on leave",
        text
        + f" Your one-time order was cancelled and ₹{money(amount):.2f} refunded to your wallet. "
          f"Your wallet balance is now ₹{balance:.2f}.",
        {"extra_order_id": order.extra_order_id, "vendor_holiday_id": holiday.vendor_holiday_id,
         "meal_slot": order.meal_slot, "meal_slots": holiday.meal_slots,
         "wallet_credit": f"{money(amount):.2f}", "wallet_balance": f"{balance:.2f}"},
        dedupe_key=f"holiday_extra:{holiday.vendor_holiday_id}:{order.extra_order_id}",
        holiday_id=holiday.vendor_holiday_id,
    )
    db.commit()
    return "refunded"


# ── Notices of replaced meals (only when replacements are enabled) ─

def _notify_meal(db: Session, rec: VendorHolidayMeal) -> None:
    when, _ = _when(rec.meal_date)
    kitchen = db.query(Provider).filter(Provider.provider_id == rec.replacement_vendor_reference_id).first()
    name = (kitchen.business_name if kitchen else None) or "another kitchen"
    notify.customer(
        db, rec.user_reference_id, "vendor_holiday_replacement", "Your meal is coming from another kitchen",
        REPLACED_MESSAGE.format(vendor=name, when=when),
        {"order_id": str(rec.order_reference_id), "subscription_id": str(rec.subscription_reference_id),
         "vendor_holiday_id": str(rec.vendor_holiday_reference_id), "meal_date": rec.meal_date.isoformat(),
         "meal_slot": rec.meal_slot, "will_be_delivered": True, "replacement_vendor_name": name,
         "replacement_vendor_id": str(rec.replacement_vendor_reference_id), "extra_cost": "0.00"},
        dedupe_key=f"holiday_meal:{rec.vendor_holiday_meal_id}",
    )


def send_notifications(db: Session, holiday_id=None) -> dict:
    """Replacement notices for processed meals not yet told; retried safely."""
    q = db.query(VendorHolidayMeal.vendor_holiday_meal_id).filter(
        VendorHolidayMeal.processing_status == "completed",
        VendorHolidayMeal.outcome == "replaced",
        VendorHolidayMeal.notification_status.in_(("pending", "failed")),
        VendorHolidayMeal.notification_attempts < MAX_ATTEMPTS,
    )
    if holiday_id is not None:
        q = q.filter(VendorHolidayMeal.vendor_holiday_reference_id == holiday_id)
    sent = failed = 0
    for (rid,) in q.order_by(VendorHolidayMeal.created_at).all():
        rec = db.query(VendorHolidayMeal).filter(
            VendorHolidayMeal.vendor_holiday_meal_id == rid
        ).with_for_update().populate_existing().one()
        if rec.notification_status == "sent":
            db.rollback()
            continue
        try:
            _notify_meal(db, rec)
            rec.notification_status = "sent"
            rec.notification_attempts = (rec.notification_attempts or 0) + 1
            rec.notified_at = now_utc()
            db.commit()
            sent += 1
        except Exception as exc:  # the meal is booked; only the notice failed - it is retried later
            db.rollback()
            logger.warning("holiday notice failed for meal record %s: %s", rid, exc)
            rec = db.query(VendorHolidayMeal).filter(VendorHolidayMeal.vendor_holiday_meal_id == rid).one()
            rec.notification_status = "failed"
            rec.notification_attempts = (rec.notification_attempts or 0) + 1
            rec.last_error = f"notification: {exc}"[:1000]
            db.commit()
            failed += 1
    return {"sent": sent, "failed": failed}


# ── The whole holiday ─────────────────────────────────────────

def _refresh_counts(db: Session, holiday: VendorHoliday) -> None:
    from app.models.vendor_holiday_model import HolidayNotice

    rows = db.query(VendorHolidayMeal).filter(
        VendorHolidayMeal.vendor_holiday_reference_id == holiday.vendor_holiday_id
    ).all()
    subs = db.query(VendorHolidaySubscription).filter(
        VendorHolidaySubscription.vendor_holiday_reference_id == holiday.vendor_holiday_id
    ).all()
    holiday.replaced_meals = sum(1 for r in rows if r.outcome == "replaced")
    holiday.compensated_meals = sum(1 for r in rows if r.outcome == "compensated")
    holiday.failed_meals = sum(1 for r in rows if r.processing_status == "failed") + \
        sum(1 for s in subs if s.skip_status == "failed")
    pending = any(r.processing_status != "completed" for r in rows) or \
        any(s.skip_status not in SKIP_DONE or s.notice_queued_at is None for s in subs)
    unsent = any(r.notification_status in ("pending", "failed") for r in rows) or db.query(
        HolidayNotice.holiday_notice_id
    ).filter(
        HolidayNotice.vendor_holiday_reference_id == holiday.vendor_holiday_id,
        HolidayNotice.status.in_(("pending", "failed")),
    ).first() is not None
    if pending:
        holiday.processing_status = "completed_with_errors" if holiday.failed_meals else "processing"
    else:
        holiday.processing_status = "completed_with_errors" if unsent else "completed"
        holiday.processed_at = holiday.processed_at or now_utc()


def _failed(db: Session, model, key_col, rid, exc) -> None:
    db.rollback()
    logger.exception("holiday work %s failed", rid)
    row = db.query(model).filter(key_col == rid).one()
    if model is VendorHolidayMeal:
        row.processing_status = "failed"
    else:
        # a skip already granted - or not due at all - stays so; only the notice is retried
        row.skip_status = "failed" if row.skip_status not in SKIP_DONE else row.skip_status
    row.attempts = (row.attempts or 0) + 1
    row.last_error = str(exc)[:1000]
    db.commit()


def process(db: Session, holiday_id, *, meal_ids=None, retry_failed: bool = False) -> dict:
    """
    Do the work of an approved emergency holiday: refund each meal, cancel the
    day's one-time orders, give every active subscription its extra skip, then
    send the notices. Every step commits on its own; safe to re-run.
    """
    holiday = db.query(VendorHoliday).filter(VendorHoliday.vendor_holiday_id == holiday_id).one()
    on, provider_id, slots = holiday.start_date, holiday.provider_reference_id, holiday.meal_slots
    removed = holiday.status != "active"
    db.commit()
    if removed:
        # deleted by an admin before its delivery time: nothing more is refunded or credited
        return {
            "outcomes": {}, "one_time_orders": {}, "skip_credits": {},
            "notifications": holiday_notices.deliver(db, holiday_id=holiday_id, retry_failed=retry_failed),
            "processing_status": holiday.processing_status, "removed": True,
        }

    q = db.query(VendorHolidayMeal.vendor_holiday_meal_id).filter(
        VendorHolidayMeal.vendor_holiday_reference_id == holiday_id,
        VendorHolidayMeal.processing_status.in_(("pending", "failed")),
        VendorHolidayMeal.attempts < MAX_ATTEMPTS,
    )
    if meal_ids:
        q = q.filter(VendorHolidayMeal.vendor_holiday_meal_id.in_(list(meal_ids)))
    outcomes: dict = {}
    for (rid,) in q.order_by(VendorHolidayMeal.created_at, VendorHolidayMeal.vendor_holiday_meal_id).all():
        try:
            outcome = process_meal(db, rid)
        except Exception as exc:
            _failed(db, VendorHolidayMeal, VendorHolidayMeal.vendor_holiday_meal_id, rid, exc)
            outcome = "failed"
        outcomes[outcome] = outcomes.get(outcome, 0) + 1

    extras: dict = {}
    for order in affected_extra_orders(db, provider_id, on, slots):
        oid = order.extra_order_id
        db.rollback()
        try:
            result = cancel_extra_order(db, holiday_id, oid)
        except Exception:
            db.rollback()
            logger.exception("holiday one-time order %s failed", oid)
            result = "failed"
        extras[result] = extras.get(result, 0) + 1

    skips: dict = {}
    sub_rows = db.query(VendorHolidaySubscription.vendor_holiday_subscription_id).filter(
        VendorHolidaySubscription.vendor_holiday_reference_id == holiday_id,
        VendorHolidaySubscription.attempts < MAX_ATTEMPTS,
        VendorHolidaySubscription.skip_status.notin_(SKIP_DONE) | VendorHolidaySubscription.notice_queued_at.is_(None),
    ).order_by(VendorHolidaySubscription.vendor_holiday_subscription_id).all()
    for (rid,) in sub_rows:
        try:
            result = process_subscription(db, rid)
        except Exception as exc:
            _failed(db, VendorHolidaySubscription, VendorHolidaySubscription.vendor_holiday_subscription_id, rid, exc)
            result = "failed"
        skips[result] = skips.get(result, 0) + 1

    meal_notices = send_notifications(db, holiday_id)
    notices = holiday_notices.deliver(db, holiday_id=holiday_id, retry_failed=retry_failed)
    holiday = db.query(VendorHoliday).filter(VendorHoliday.vendor_holiday_id == holiday_id).with_for_update().one()
    _refresh_counts(db, holiday)
    db.commit()
    return {
        "outcomes": outcomes,
        "one_time_orders": extras,
        "skip_credits": skips,
        "notifications": {"sent": notices["sent"] + meal_notices["sent"],
                          "failed": notices["failed"] + meal_notices["failed"]},
        "processing_status": holiday.processing_status,
    }


def retry_pending(db: Session) -> dict:
    """Scheduled safety net: unfinished work and unsent notices of recent emergency holidays."""
    since = today_local() - timedelta(days=2)
    ids = [
        hid for (hid,) in db.query(VendorHoliday.vendor_holiday_id).filter(
            VendorHoliday.holiday_type == holidays.EMERGENCY,
            VendorHoliday.status == "active",
            VendorHoliday.start_date >= since,
            VendorHoliday.processing_status.in_(("pending", "processing", "completed_with_errors")),
        ).all()
    ]
    db.rollback()
    results = {str(hid): process(db, hid, retry_failed=True) for hid in ids}
    return {"holidays": len(ids), "results": results}


# ── Meals created after the holiday ───────────────────────────

def refund_blocked_meal(db: Session, order: Order, sub: Subscription, holiday: VendorHoliday) -> Decimal:
    """
    A meal created (a plan bought, switched or resumed) after an emergency
    holiday blocking that meal was approved: it is cancelled and its value
    goes back to the wallet, exactly like the meals the holiday found when
    it was approved (same refund key, so never twice), and the customer is
    told. Runs in the caller's transaction.
    """
    order.status = "cancelled"
    order.cancel_reason = CANCEL_REASON
    order.vendor_holiday_reference_id = holiday.vendor_holiday_id
    amount = meals.refund_meal(
        db, order, sub, reason=REFUND_REASON,
        description=f"Meal refund: kitchen emergency holiday on {order.order_date} ({order.meal_slot})",
    )
    txn = ledger.customer_txn_exists(db, f"meal_refund:{order.order_id}")
    value = money(amount if amount > ZERO else (order.refund_amount or ZERO))
    db.execute(
        pg_insert(VendorHolidayMeal).values(
            vendor_holiday_meal_id=uuid.uuid4(), vendor_holiday_reference_id=holiday.vendor_holiday_id,
            order_reference_id=order.order_id, subscription_reference_id=sub.subscription_id,
            user_reference_id=order.user_reference_id, original_vendor_reference_id=order.vendor_reference_id,
            meal_date=order.order_date, meal_slot=order.meal_slot, outcome="compensated",
            meal_amount=value, wallet_transaction_reference_id=txn.wallet_transaction_id if txn else None,
            processing_status="completed", compensation_status="completed", notification_status="not_required",
            attempts=1, notification_attempts=0, processed_at=now_utc(),
        ).on_conflict_do_nothing(constraint="uq_vendor_holiday_meal")
    )
    kitchen = db.query(Provider.business_name).filter(Provider.provider_id == holiday.provider_reference_id).scalar()
    title, body = leave_notice(kitchen or "Your kitchen", order.order_date, holiday.meal_slots or [order.meal_slot])
    if value > ZERO:
        body += f" We've refunded ₹{value:.2f} for that {order.meal_slot} to your wallet."
    holiday_notices.queue(
        db, "customer", order.user_reference_id, "vendor_holiday_compensation", title, body,
        {"subscription_id": sub.subscription_id, "order_id": order.order_id,
         "vendor_holiday_id": holiday.vendor_holiday_id, "provider_id": holiday.provider_reference_id,
         "meal_date": order.order_date.isoformat(), "meal_slot": order.meal_slot, "meal_slots": holiday.meal_slots,
         "will_be_delivered": False, "wallet_credit": f"{value:.2f}"},
        dedupe_key=f"holiday_meal_refund:{holiday.vendor_holiday_id}:{order.order_id}",
        holiday_id=holiday.vendor_holiday_id,
    )
    business_event("holiday.blocked_meal_refunded", holiday_id=holiday.vendor_holiday_id, order_id=order.order_id,
                   amount=value)
    return value


# ── An admin deletes the holiday ──────────────────────────────

def remove(db: Session, holiday_id, *, actor_id, reason: str | None = None, ip: str | None = None) -> VendorHoliday:
    """
    Delete an approved emergency holiday (commits) - only before
    delete_cutoff(), checked after the locks so nothing changes once it has
    passed. The blocked meals open again for new orders and new plans.
    Everything already given stays (as when any holiday is removed):
    refunds and free skips stay with the customers and cancelled meals stay
    cancelled; work not yet done is not done. Customers, partners and the
    kitchen that were told about the closure are told it is open again.
    """
    found = db.query(VendorHoliday.provider_reference_id, VendorHoliday.holiday_type).filter(
        VendorHoliday.vendor_holiday_id == holiday_id
    ).first()
    if found is None:
        raise DomainError("Holiday not found", 404)
    if found.holiday_type != holidays.EMERGENCY:
        raise DomainError("Only emergency holidays can be deleted here. Regular holidays change through the "
                          "kitchen's requests.", 409, code="HOLIDAY_NOT_EMERGENCY")
    # lock order as in declare(): kitchen, then the holiday
    kitchen = db.query(Provider).filter(Provider.provider_id == found.provider_reference_id).with_for_update().one()
    holiday = db.query(VendorHoliday).filter(
        VendorHoliday.vendor_holiday_id == holiday_id
    ).with_for_update().populate_existing().one()
    if holiday.status != "active":
        db.rollback()
        raise DomainError("This emergency holiday was already deleted", 409, code="HOLIDAY_ALREADY_DELETED")
    cutoff = delete_cutoff(db, holiday)
    if now_local() >= cutoff:
        db.rollback()
        raise DomainError(
            "This emergency holiday can no longer be deleted because the delivery cutoff has passed.", 409,
            code="HOLIDAY_DELETE_CUTOFF_PASSED", extra={"delete_cutoff_at": cutoff.isoformat()},
        )
    holiday.status = "removed"
    holiday.removed_at = now_utc()
    holiday.removed_by = actor_id
    holiday.removed_reason = (reason or "").strip() or None
    holiday.updated_by = actor_id
    _queue_reopen_notices(db, holiday, kitchen)
    record_audit(
        db, table="provider.vendor_holidays", record_id=holiday.vendor_holiday_id, operation="D",
        old={"status": "active", "date": holiday.start_date, "meal_slots": holiday.meal_slots},
        new={"status": "removed", "reason": holiday.removed_reason, "delete_cutoff_at": cutoff.isoformat()},
        actor_id=actor_id, actor_type="admin", ip=ip,
    )
    db.commit()
    business_event("holiday.emergency_deleted", holiday_id=holiday.vendor_holiday_id,
                   provider_id=holiday.provider_reference_id, date=holiday.start_date, meal_slots=holiday.meal_slots)
    holiday_notices.deliver(db, holiday_id=holiday.vendor_holiday_id)
    return db.query(VendorHoliday).filter(VendorHoliday.vendor_holiday_id == holiday_id).one()


def _queue_reopen_notices(db: Session, holiday: VendorHoliday, kitchen: Provider) -> None:
    """Everyone told about the closure hears it is lifted: customers, partners and the kitchen."""
    from app.models.vendor_holiday_model import HolidayNotice

    name = kitchen.business_name or "Your kitchen"
    when, _ = _when(holiday.start_date)
    what = _meals(holiday.meal_slots) if holiday.meal_slots else "all meals"
    told = db.query(HolidayNotice.audience, HolidayNotice.recipient_id).filter(
        HolidayNotice.vendor_holiday_reference_id == holiday.vendor_holiday_id,
        HolidayNotice.audience.in_(("customer", "delivery_boy")),
        HolidayNotice.recipient_id.isnot(None),
    ).distinct().all()
    data = {"vendor_holiday_id": holiday.vendor_holiday_id, "provider_id": kitchen.provider_id,
            "date": holiday.start_date.isoformat(), "meal_slots": holiday.meal_slots, "holiday_removed": True}
    for audience, recipient in sorted(told, key=lambda r: (r[0], str(r[1]))):
        if audience == "customer":
            title = REOPEN_TITLE.format(when=when)
            body = REOPEN_MESSAGE.format(kitchen=name, when=when, meals=what)
        else:
            title = f"{name} is open again {when}"
            body = f"{name} is open again {when} for {what}. Pickups from this kitchen that day are as usual."
        holiday_notices.queue(
            db, audience, recipient, "vendor_holiday" if audience == "customer" else "schedule_update", title, body,
            data, dedupe_key=f"holiday_reopen:{holiday.vendor_holiday_id}:{recipient}",
            holiday_id=holiday.vendor_holiday_id,
        )
    holiday_notices.queue(
        db, "provider", kitchen.provider_id, "holiday_request", "Emergency holiday cancelled",
        f"Orleeno cancelled your emergency holiday {when} ({what}). You are open again for those meals and can "
        "get new orders. Meals already cancelled and refunded for that day stay cancelled.",
        data, dedupe_key=f"holiday_reopen:{holiday.vendor_holiday_id}:kitchen", holiday_id=holiday.vendor_holiday_id,
    )
