"""
Emergency holidays: a kitchen suddenly cannot cook on a date.

Declaring one (today or a later date, never the past) closes the kitchen for
that date at once - no new order, subscription meal or replacement can land
on it (holidays.is_closed) - and lists every affected meal:

    Step 1  meals of the kitchen's active subscriptions on that date that are
            still at the kitchen and not yet cooked out (scheduled /
            preparing) and not refunded. Nothing else is touched: delivered,
            skipped, cancelled, packed or picked-up meals stay as they are,
            and the subscription itself is never cancelled or re-priced.

Each meal is then processed on its own (own transaction, row locks):

    Step 2  find a replacement kitchen that is open and approved, delivers to
            the customer's PIN code, is not on any holiday that day, sells a
            package for the meal time with the same dietary type, can still
            make the delivery window, has room (package + kitchen limits), and
            whose per-meal price is NOT higher than the customer's subscribed
            per-meal price. Ties are broken deterministically: same package >
            same category > other; then rating; then spare capacity; then
            distance (the kitchen's own PIN first); then kitchen id.
    Step 3  found: that one meal moves to the replacement kitchen (and its
            delivery partner); the customer pays nothing extra and the
            subscription is unchanged. The kitchen is paid by the existing
            settlement rule (the subscription's per-meal earning).
    Step 4  none: the meal becomes not deliverable (cancelled,
            'vendor_emergency_holiday'), and the customer gets exactly one
            extra free skip (skip wallet, VENDOR_EMERGENCY_HOLIDAY_COMPENSATION)
            and the meal's value in the wallet (VENDOR_EMERGENCY_HOLIDAY_MEAL_
            REFUND) - two ledger entries, each with its own idempotency key.

Customers are notified only after the meal's transaction committed (never a
credit that is not booked), once per meal (notification dedupe key). A
failed notice is retried later without touching money again. A user's own
skip is never compensated: only meals still owed are affected.
"""

import logging
import uuid
from datetime import date, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.audit import business_event, record_audit
from app.core.clock import now_local, now_utc, today_local
from app.core.errors import DomainError
from app.domain import capacity, holidays, ledger, notify, ratings, vendor_partner
from app.domain import orders as meals
from app.domain.eligibility import (
    kitchen_serves, package_block_reason, parse_pincode, provider_block_reason, serves_pincode_filter,
    serviceable_pincode,
)
from app.domain.pricing import ZERO, money, subscription_unit_price
from app.domain.slots import SLOT_WINDOWS, package_serves
from app.core.clock import local_datetime
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.provider_selected_package_model import ProviderSelectedPackage
from app.models.skip_credit_model import SkipCreditTransaction
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.user_address_model import UserAddress
from app.models.vendor_holiday_model import VendorHoliday, VendorHolidayMeal

logger = logging.getLogger("app.holidays")

SKIP_REASON = "VENDOR_EMERGENCY_HOLIDAY_COMPENSATION"
REFUND_REASON = "VENDOR_EMERGENCY_HOLIDAY_MEAL_REFUND"
CANCEL_REASON = "vendor_emergency_holiday"
AFFECTED_STATUSES = ("scheduled", "preparing")
MAX_DAYS_AHEAD = 30
MAX_ATTEMPTS = 5

# {when}: "today" (the usual case, word for word as agreed) or "on 06 Oct 2026"
REPLACED_MESSAGE = (
    "Sorry for the inconvenience! Your regular vendor is unavailable {when} due to an emergency. "
    "We have arranged your meal from {vendor} at no extra cost. Your meal will be delivered as scheduled."
)
COMPENSATED_MESSAGE = (
    "We're sorry for the inconvenience. Your regular vendor is unavailable {when} due to an emergency, "
    "and we couldn't find a replacement vendor in your area at the same or lower price. We've added 1 extra "
    "meal skip to your skip wallet as a gift and credited ₹{amount} for {meal} to your wallet. "
    "Thank you for your understanding."
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
            Order.status.in_(AFFECTED_STATUSES),
            Order.refunded_at.is_(None),
            Subscription.status == "active",
        )
        .order_by(Order.order_id)
        .all()
    )


def preview(db: Session, provider_id, on: date) -> dict:
    orders = affected_orders(db, provider_id, on)
    by_slot: dict = {}
    for o in orders:
        by_slot[o.meal_slot] = by_slot.get(o.meal_slot, 0) + 1
    return {
        "date": on,
        "affected_orders": len(orders),
        "affected_subscriptions": len({o.subscription_reference_id for o in orders}),
        "by_meal_slot": by_slot,
    }


def _validate_date(on: date) -> None:
    today = today_local()
    if on < today:
        raise DomainError("An emergency holiday cannot be declared for a past date", code="HOLIDAY_IN_PAST")
    if on > today + timedelta(days=MAX_DAYS_AHEAD):
        raise DomainError(f"An emergency holiday can be declared at most {MAX_DAYS_AHEAD} days ahead. "
                          "Plan longer closures as holidays.")


def declare(db: Session, provider_id, on: date, reason: str | None, *, actor_type: str, actor_id) -> VendorHoliday:
    """Close the kitchen for `on` and list the affected meals (committed); then process them."""
    _validate_date(on)
    # one declaration at a time per kitchen
    kitchen = db.query(Provider).filter(Provider.provider_id == provider_id).with_for_update().first()
    if kitchen is None:
        raise DomainError("Kitchen not found", 404)
    existing = holidays.holiday_on(db, provider_id, on)
    if existing is not None:
        if existing.holiday_type == holidays.EMERGENCY:
            raise DomainError(f"An emergency holiday is already declared for {on}", 409, code="HOLIDAY_EXISTS")
        raise DomainError(f"{on} is already a planned holiday: no meals are scheduled that day", 409,
                          code="HOLIDAY_EXISTS")

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
    holiday.affected_meals = len(orders)
    holiday.affected_subscriptions = len({o.subscription_reference_id for o in orders})
    if not orders:
        holiday.processing_status = "completed"
        holiday.processed_at = now_utc()
    record_audit(
        db, table="provider.vendor_holidays", record_id=holiday.vendor_holiday_id, operation="I",
        new={"type": "emergency", "date": on, "reason": holiday.reason, "affected_meals": len(orders)},
        actor_id=actor_id, actor_type=actor_type,
    )
    business_event("holiday.emergency_declared", provider_id=provider_id, date=on, meals=len(orders))
    db.commit()
    return holiday


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


# ── Steps 3 and 4: one meal ───────────────────────────────────

def _grant_skip(db: Session, sub: Subscription, order: Order, holiday: VendorHoliday) -> SkipCreditTransaction:
    key = f"holiday_skip:{holiday.vendor_holiday_id}:{order.order_id}"
    existing = db.query(SkipCreditTransaction).filter(SkipCreditTransaction.idempotency_key == key).first()
    if existing is not None:
        return existing
    before = (sub.free_skips_total or 0) - (sub.free_skips_used or 0)
    sub.free_skips_total = (sub.free_skips_total or 0) + 1
    txn = SkipCreditTransaction(
        subscription_reference_id=sub.subscription_id, user_reference_id=sub.user_reference_id,
        order_reference_id=order.order_id, vendor_reference_id=holiday.provider_reference_id,
        meal_date=order.order_date, type="credit", skips=1, reason=SKIP_REASON,
        free_skips_before=before, free_skips_after=before + 1,
        reference_type="vendor_holiday", reference_id=holiday.vendor_holiday_id,
        description=f"1 extra skip: kitchen emergency holiday on {order.order_date} ({order.meal_slot})",
        idempotency_key=key,
    )
    db.add(txn)
    db.flush()
    return txn


def process_meal(db: Session, record_id) -> str:
    """
    Process one affected meal exactly once (commits). Returns the outcome.
    Lock order: holiday-meal record -> subscription -> meal.
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
        order.status in AFFECTED_STATUSES and order.refunded_at is None and sub.status == "active"
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

    eligible, rejected = candidates(db, order, sub)
    chosen = None
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
    else:
        order.status = "cancelled"
        order.cancel_reason = CANCEL_REASON
        order.vendor_holiday_reference_id = holiday.vendor_holiday_id
        skip = _grant_skip(db, sub, order, holiday)
        amount = meals.refund_meal(
            db, order, sub, reason=REFUND_REASON,
            description=f"Meal refund: kitchen emergency holiday on {order.order_date} ({order.meal_slot})",
        )
        txn = ledger.customer_txn_exists(db, f"meal_refund:{order.order_id}")
        if order.delivery_boy_reference_id:
            notify.delivery_partner(
                db, order.delivery_boy_reference_id, "schedule_update", "Not deliverable - vendor holiday",
                f"The {order.meal_slot} on {order.order_date} cannot be delivered: the kitchen is closed.",
                {"order_id": str(order.order_id), "kind": "subscription"},
            )
        rec.outcome = "compensated"
        rec.meal_amount = money(amount if amount > ZERO else (order.refund_amount or ZERO))
        rec.skip_credit_reference_id = skip.skip_credit_transaction_id
        rec.wallet_transaction_reference_id = txn.wallet_transaction_id if txn else None
        rec.compensation_status = "completed"
        rec.last_error = "; ".join(sorted({r["reason"] for r in rejected}))[:1000] or None
    rec.processing_status = "completed"
    rec.notification_status = "pending"
    rec.processed_at = now_utc()
    db.commit()
    business_event("holiday.meal_processed", holiday_id=holiday.vendor_holiday_id, order_id=order.order_id,
                   outcome=rec.outcome)
    return rec.outcome


def _notify_meal(db: Session, rec: VendorHolidayMeal) -> None:
    order = db.query(Order).filter(Order.order_id == rec.order_reference_id).one()
    when, meal_ref = _when(rec.meal_date)
    base = {
        "order_id": str(rec.order_reference_id), "subscription_id": str(rec.subscription_reference_id),
        "vendor_holiday_id": str(rec.vendor_holiday_reference_id), "meal_date": rec.meal_date.isoformat(),
        "meal_slot": rec.meal_slot,
    }
    if rec.outcome == "replaced":
        kitchen = db.query(Provider).filter(Provider.provider_id == rec.replacement_vendor_reference_id).first()
        name = (kitchen.business_name if kitchen else None) or "another kitchen"
        body = REPLACED_MESSAGE.format(vendor=name, when=when)
        notify.customer(
            db, rec.user_reference_id, "vendor_holiday_replacement", "Your meal is coming from another kitchen", body,
            {**base, "will_be_delivered": True, "replacement_vendor_name": name,
             "replacement_vendor_id": str(rec.replacement_vendor_reference_id), "extra_cost": "0.00"},
            dedupe_key=f"holiday_meal:{rec.vendor_holiday_meal_id}",
        )
    else:
        amount = money(rec.meal_amount or order.refund_amount or ZERO)
        body = COMPENSATED_MESSAGE.format(amount=f"{amount:.2f}", when=when, meal=meal_ref)
        notify.customer(
            db, rec.user_reference_id, "vendor_holiday_compensation", "Sorry - your meal can't be delivered", body,
            {**base, "will_be_delivered": False, "replacement_vendor_name": None,
             "skips_credited": 1, "wallet_credit": f"{amount:.2f}",
             "wallet_transaction_id": str(rec.wallet_transaction_reference_id) if rec.wallet_transaction_reference_id else None},
            dedupe_key=f"holiday_meal:{rec.vendor_holiday_meal_id}",
        )


def send_notifications(db: Session, holiday_id=None) -> dict:
    """Customer notices for processed meals not yet told (committed money only); retried safely."""
    q = db.query(VendorHolidayMeal.vendor_holiday_meal_id).filter(
        VendorHolidayMeal.processing_status == "completed",
        VendorHolidayMeal.outcome.in_(("replaced", "compensated")),
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
        except Exception as exc:  # the money is booked; only the notice failed - it is retried later
            db.rollback()
            logger.warning("holiday notice failed for meal record %s: %s", rid, exc)
            rec = db.query(VendorHolidayMeal).filter(VendorHolidayMeal.vendor_holiday_meal_id == rid).one()
            rec.notification_status = "failed"
            rec.notification_attempts = (rec.notification_attempts or 0) + 1
            rec.last_error = f"notification: {exc}"[:1000]
            db.commit()
            failed += 1
    return {"sent": sent, "failed": failed}


def _refresh_counts(db: Session, holiday: VendorHoliday) -> None:
    rows = db.query(VendorHolidayMeal).filter(
        VendorHolidayMeal.vendor_holiday_reference_id == holiday.vendor_holiday_id
    ).all()
    holiday.replaced_meals = sum(1 for r in rows if r.outcome == "replaced")
    holiday.compensated_meals = sum(1 for r in rows if r.outcome == "compensated")
    holiday.failed_meals = sum(1 for r in rows if r.processing_status == "failed")
    pending = any(r.processing_status != "completed" for r in rows)
    unsent = any(r.notification_status in ("pending", "failed") for r in rows)
    if pending:
        holiday.processing_status = "completed_with_errors" if holiday.failed_meals else "processing"
    else:
        holiday.processing_status = "completed_with_errors" if unsent else "completed"
        holiday.processed_at = holiday.processed_at or now_utc()


def process(db: Session, holiday_id, *, meal_ids=None) -> dict:
    """Process every pending (or failed) meal of a holiday, then send the notices. Safe to re-run."""
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
            db.rollback()
            logger.exception("holiday meal %s failed", rid)
            rec = db.query(VendorHolidayMeal).filter(VendorHolidayMeal.vendor_holiday_meal_id == rid).one()
            rec.processing_status = "failed"
            rec.attempts = (rec.attempts or 0) + 1
            rec.last_error = str(exc)[:1000]
            db.commit()
            outcome = "failed"
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    notices = send_notifications(db, holiday_id)
    holiday = db.query(VendorHoliday).filter(VendorHoliday.vendor_holiday_id == holiday_id).with_for_update().one()
    _refresh_counts(db, holiday)
    db.commit()
    return {"outcomes": outcomes, "notifications": notices, "processing_status": holiday.processing_status}


def retry_pending(db: Session) -> dict:
    """Scheduled safety net: unfinished meals and unsent notices of recent emergency holidays."""
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
    results = {str(hid): process(db, hid) for hid in ids}
    return {"holidays": len(ids), "results": results}
