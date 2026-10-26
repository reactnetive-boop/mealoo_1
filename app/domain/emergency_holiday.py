"""
Emergency holidays: a kitchen suddenly cannot cook on a date.

A kitchen only REQUESTS an emergency holiday (app/services/holiday_request_
service.py); nothing changes until an admin approves it. Approval declares
it here: the kitchen is closed for that date at once - no new order,
subscription meal, preparation task, pickup or delivery can land on it
(holidays.is_closed) - and the work is listed:

    meals          subscription meals of that date still at the kitchen and
                   not cooked out (scheduled / preparing; ahead of the date
                   also ready_for_pickup), not refunded. Delivered, skipped,
                   cancelled or picked-up meals stay as they are, and the
                   subscription itself is never cancelled or re-priced.
    subscriptions  every active subscription of the kitchen: each gets
                   exactly ONE extra free skip for the holiday, whether or not
                   it had a meal that day.
    one-time       one-time orders for that date at the kitchen are cancelled
                   and refunded in full.

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
from datetime import date, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.audit import business_event, record_audit
from app.core.clock import now_local, now_utc, today_local
from app.core.errors import DomainError
from app.domain import capacity, holiday_notices, holidays, ledger, notify, ratings, vendor_partner
from app.domain import orders as meals
from app.domain.eligibility import (
    kitchen_serves, package_block_reason, parse_pincode, provider_block_reason, serves_pincode_filter,
    serviceable_pincode,
)
from app.domain.pricing import ZERO, money, subscription_unit_price
from app.domain.slots import SLOT_WINDOWS, package_serves
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


# ── Step 1: affected meals ────────────────────────────────────

def affected_orders(db: Session, provider_id, on: date) -> list[Order]:
    return (
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
        .order_by(Order.order_id)
        .all()
    )


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


def affected_extra_orders(db: Session, provider_id, on: date) -> list[ExtraOrder]:
    return (
        db.query(ExtraOrder)
        .filter(
            ExtraOrder.vendor_reference_id == provider_id,
            ExtraOrder.delivery_date == on,
            ExtraOrder.status.in_(_extra_statuses(on)),
            ExtraOrder.refunded_at.is_(None),
        )
        .order_by(ExtraOrder.extra_order_id)
        .all()
    )


def preview(db: Session, provider_id, on: date) -> dict:
    """What approving an emergency holiday for `on` would do (nothing is saved)."""
    orders = affected_orders(db, provider_id, on)
    extras = affected_extra_orders(db, provider_id, on)
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
        "affected_orders": len(orders),
        "affected_subscriptions": len(subs),
        "by_meal_slot": by_slot,
        "one_time_orders": len(extras),
        # every active subscription of the kitchen gets one extra free skip
        "skip_credits": len(skip_subscriptions(db, provider_id)),
        "estimated_refund": str(money(refund)),
    }


def _validate_date(on: date) -> None:
    today = today_local()
    if on < today:
        raise DomainError("An emergency holiday cannot be declared for a past date", code="HOLIDAY_IN_PAST")
    if on > today + timedelta(days=MAX_DAYS_AHEAD):
        raise DomainError(f"An emergency holiday can be declared at most {MAX_DAYS_AHEAD} days ahead. "
                          "Plan longer closures as holidays.")


def validate_request(db: Session, provider_id, on: date) -> None:
    """Checks an emergency holiday for `on` (raises DomainError): date range, not already closed."""
    _validate_date(on)
    existing = holidays.holiday_on(db, provider_id, on)
    if existing is not None:
        if existing.holiday_type == holidays.EMERGENCY:
            raise DomainError(f"An emergency holiday is already approved for {on}", 409, code="HOLIDAY_EXISTS")
        raise DomainError(f"{on} is already a holiday: no meals are scheduled that day", 409, code="HOLIDAY_EXISTS")


def declare(db: Session, provider_id, on: date, reason: str | None, *, actor_type: str, actor_id,
            commit: bool = True, request_id=None) -> VendorHoliday:
    """
    Close the kitchen for `on` and list the work (meals to refund, subscriptions
    for the skip, partners to tell). Runs when an admin approves a kitchen's
    request or declares one; process() then does the work.
    """
    _validate_date(on)
    # one declaration at a time per kitchen
    kitchen = db.query(Provider).filter(Provider.provider_id == provider_id).with_for_update().first()
    if kitchen is None:
        raise DomainError("Kitchen not found", 404)
    validate_request(db, provider_id, on)

    holiday = VendorHoliday(
        vendor_holiday_id=uuid.uuid4(), provider_reference_id=provider_id, holiday_type=holidays.EMERGENCY,
        rule_type="dates", dates=[on], start_date=on, end_date=on, reason=(reason or "").strip() or None,
        status="active", processing_status="pending", created_by_type=actor_type, created_by=actor_id,
    )
    db.add(holiday)
    db.flush()
    orders = affected_orders(db, provider_id, on)
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
    if subs:
        db.execute(
            pg_insert(VendorHolidaySubscription).values([
                {
                    "vendor_holiday_subscription_id": uuid.uuid4(),
                    "vendor_holiday_reference_id": holiday.vendor_holiday_id,
                    "subscription_reference_id": sub.subscription_id,
                    "user_reference_id": sub.user_reference_id,
                    "skip_status": "pending",
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
        new={"type": "emergency", "date": on, "reason": holiday.reason, "affected_meals": len(orders),
             "skip_credits": len(subs), "request_id": str(request_id) if request_id else None},
        actor_id=actor_id, actor_type=actor_type,
    )
    business_event("holiday.emergency_declared", provider_id=provider_id, date=on, meals=len(orders),
                   subscriptions=len(subs))
    if commit:
        db.commit()
    return holiday


def _queue_partner_notices(db: Session, holiday: VendorHoliday, kitchen: Provider, *, request_id=None) -> None:
    """The kitchen's partners: no pickup there that day (meals already packed or picked up stay theirs)."""
    on = holiday.start_date
    partners = set()
    row = vendor_partner.kitchen_row(db, kitchen.provider_id)
    if row is not None:
        partners.add(row.delivery_boy_reference_id)
    for (boy,) in db.query(Order.delivery_boy_reference_id).filter(
        Order.vendor_reference_id == kitchen.provider_id, Order.order_date == on,
        Order.delivery_boy_reference_id.isnot(None),
    ).distinct():
        partners.add(boy)
    for (boy,) in db.query(ExtraOrder.delivery_boy_reference_id).filter(
        ExtraOrder.vendor_reference_id == kitchen.provider_id, ExtraOrder.delivery_date == on,
        ExtraOrder.delivery_boy_reference_id.isnot(None),
    ).distinct():
        partners.add(boy)
    name = kitchen.business_name or "Your kitchen"
    when, _ = _when(on)
    for boy in sorted((p for p in partners if p is not None), key=str):
        on_route = db.query(Order.order_id).filter(
            Order.vendor_reference_id == kitchen.provider_id, Order.order_date == on,
            Order.delivery_boy_reference_id == boy,
            Order.status.in_(("ready_for_pickup", "picked_up", "out_for_delivery")),
        ).count()
        body = f"{name} is on leave {when}. No pickup is required from this kitchen that day."
        if on_route:
            body += f" {on_route} meal(s) already packed or picked up stay on your list."
        holiday_notices.queue(
            db, "delivery_boy", boy, "schedule_update", f"{name} is on leave {when}", body,
            {"vendor_holiday_id": holiday.vendor_holiday_id, "provider_id": kitchen.provider_id,
             "date": on.isoformat(), "pickup_required": False},
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
    closed = holidays.closed_kitchens(db, {p.provider_id for p, _ in rows}, on)
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
                skip_status="pending", attempts=0, refunded_meals=0, refund_amount=ZERO,
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
    Grant the subscription's extra skip (once) and, when every meal of it is
    processed, log the customer's notice in the same transaction (commits).
    Lock order: holiday subscription row -> subscription.
    """
    row = db.query(VendorHolidaySubscription).filter(
        VendorHolidaySubscription.vendor_holiday_subscription_id == row_id
    ).with_for_update().populate_existing().one()
    if row.skip_status == "completed" and row.notice_queued_at is not None:
        db.rollback()
        return "done"
    holiday = db.query(VendorHoliday).filter(VendorHoliday.vendor_holiday_id == row.vendor_holiday_reference_id).one()
    sub = db.query(Subscription).filter(
        Subscription.subscription_id == row.subscription_reference_id
    ).with_for_update().populate_existing().one()
    row.attempts = (row.attempts or 0) + 1
    if row.skip_status != "completed":
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
    body = LEAVE_MESSAGE.format(kitchen=name, when=when)
    if replaced and not row.refunded_meals:
        # only with the replacement search switched on: the meal still comes, from another kitchen
        body = f"{name} is on leave {when}. Your meal comes from another kitchen at no extra cost."
    elif row.refunded_meals:
        body += REFUND_MESSAGE.format(amount=f"{refunded:.2f}", meals=_meals_text(row.refunded_meals),
                                      balance=f"{balance:.2f}")
    else:
        body += NOTHING_DUE_MESSAGE
    body += SKIP_MESSAGE
    free_left = (sub.free_skips_total or 0) - (sub.free_skips_used or 0)
    holiday_notices.queue(
        db, "customer", sub.user_reference_id, "vendor_holiday_compensation",
        LEAVE_TITLE.format(when=when), body,
        {
            "subscription_id": sub.subscription_id, "vendor_holiday_id": holiday.vendor_holiday_id,
            "provider_id": holiday.provider_reference_id, "meal_date": holiday.start_date.isoformat(),
            "will_be_delivered": False, "replacement_vendor_name": None,
            "refunded_meals": row.refunded_meals, "wallet_credit": f"{refunded:.2f}",
            "wallet_balance": f"{balance:.2f}", "skips_credited": 1, "free_skips_left": free_left,
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
    when, _ = _when(holiday.start_date)
    balance = money(db.query(Wallet.balance).filter(Wallet.user_reference_id == order.user_reference_id).scalar() or ZERO)
    holiday_notices.queue(
        db, "customer", order.user_reference_id, "order_cancelled", "Order cancelled - kitchen on leave",
        LEAVE_MESSAGE.format(kitchen=name, when=when)
        + f" Your one-time order was cancelled and ₹{money(amount):.2f} refunded to your wallet. "
          f"Your wallet balance is now ₹{balance:.2f}.",
        {"extra_order_id": order.extra_order_id, "vendor_holiday_id": holiday.vendor_holiday_id,
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
        any(s.skip_status != "completed" or s.notice_queued_at is None for s in subs)
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
        row.skip_status = "failed" if row.skip_status != "completed" else row.skip_status
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
    on, provider_id = holiday.start_date, holiday.provider_reference_id
    db.commit()

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
    for order in affected_extra_orders(db, provider_id, on):
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
        (VendorHolidaySubscription.skip_status != "completed") | VendorHolidaySubscription.notice_queued_at.is_(None),
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
