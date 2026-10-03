"""
Meal generation, refunds and settlement - shared by customer actions,
kitchen / partner actions, admin actions and the scheduled jobs.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.clock import now_utc, today_local
from app.core.config import DELIVERY_BOY_FEE_PER_DELIVERY
from app.core.security import generate_numeric_code
from app.domain import ledger, notify
from app.domain.pricing import money, ZERO, customer_payable_per_delivery
from app.domain.slots import expand_plan_slot, is_before_cutoff
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage

PICKUP_CODE_LENGTH = 4
DELIVERY_CODE_LENGTH = 6


def new_codes() -> dict:
    return {
        "otp_for_delivery": generate_numeric_code(DELIVERY_CODE_LENGTH),
        "pickup_code": generate_numeric_code(PICKUP_CODE_LENGTH),
    }


# ── Generation ────────────────────────────────────────────────

def generate_meals(db: Session, subscription: Subscription, from_date: date | None = None, to_date: date | None = None) -> int:
    """
    Create the missing daily meals of an active subscription.

    Idempotent: (subscription, date, slot) is unique and inserts use ON
    CONFLICT DO NOTHING, so running it any number of times - midnight job,
    restart, subscription creation - never duplicates a meal. Dates in the
    past, and today's slots whose cut-off has passed, are never created.
    """

    if subscription.status != "active":
        return 0

    slots = expand_plan_slot(subscription.meal_slot)
    if not slots:
        return 0

    today = today_local()
    start = max(subscription.start_date, from_date or subscription.start_date, today)
    end = subscription.end_date if to_date is None else min(subscription.end_date, to_date)

    rows = []
    current = start
    while current < end:
        for slot in slots:
            if current == today and not is_before_cutoff(current, slot):
                continue
            rows.append({
                "subscription_reference_id": subscription.subscription_id,
                "user_reference_id": subscription.user_reference_id,
                "vendor_reference_id": subscription.vendor_reference_id,
                "delivery_address_reference_id": subscription.user_address_reference_id,
                "order_date": current,
                "meal_slot": slot,
                "status": "scheduled",
                "is_free_skip": False,
                **new_codes(),
            })
        current += timedelta(days=1)

    if not rows:
        return 0

    for r in rows:
        r["order_id"] = uuid.uuid4()

    stmt = (
        pg_insert(Order)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["subscription_reference_id", "order_date", "meal_slot"])
    )
    result = db.execute(stmt)
    db.flush()
    return result.rowcount or 0


def total_deliveries(subscription: Subscription) -> int:
    snapshot = subscription.pricing_snapshot or {}
    if snapshot.get("deliveries"):
        return int(snapshot["deliveries"])
    days = (subscription.end_date - subscription.start_date).days - (subscription.total_days_paused or 0)
    return max(days, 1) * max(len(expand_plan_slot(subscription.meal_slot)), 1)


def meal_value(subscription: Subscription) -> Decimal:
    """What one meal of this subscription is worth to the customer."""
    return customer_payable_per_delivery(
        subscription.pricing_snapshot,
        subscription.final_amount,
        total_deliveries(subscription),
    )


# ── Refunds ───────────────────────────────────────────────────

def refund_meal(db: Session, order: Order, subscription: Subscription, *, reason: str, description: str) -> Decimal:
    """Return one meal's value to the wallet, at most once per meal."""

    if order.refunded_at is not None:
        return ZERO
    amount = meal_value(subscription)
    if amount <= ZERO:
        return ZERO

    ledger.post_customer(
        db,
        subscription.user_reference_id,
        type="credit",
        amount=amount,
        reason=reason,
        idempotency_key=f"meal_refund:{order.order_id}",
        reference_type="order",
        reference_id=order.order_id,
        description=description,
    )
    order.refund_amount = amount
    order.refunded_at = now_utc()
    subscription.refunded_amount = money(subscription.refunded_amount) + amount
    return amount


def refund_extra_order(db: Session, order: ExtraOrder, *, reason: str, description: str) -> Decimal:
    if order.refunded_at is not None:
        return ZERO
    amount = money(order.total_price)
    if amount <= ZERO:
        return ZERO
    ledger.post_customer(
        db,
        order.user_reference_id,
        type="credit",
        amount=amount,
        reason=reason,
        idempotency_key=f"extra_refund:{order.extra_order_id}",
        reference_type="extra_order",
        reference_id=order.extra_order_id,
        description=description,
    )
    order.refund_amount = amount
    order.refunded_at = now_utc()
    return amount


def cancel_future_meals(
    db: Session,
    subscription: Subscription,
    *,
    from_date: date,
    reason: str,
    refund: bool,
    refund_reason: str = "subscription_cancel_refund",
) -> tuple[int, Decimal]:
    """
    Cancel every still-cancellable meal from `from_date` on.

    A meal is cancellable while it is 'scheduled' and its same-day cut-off has
    not passed; meals already being cooked or delivered are left alone.
    Returns (meals cancelled, amount refunded).
    """

    meals = (
        db.query(Order)
        .filter(
            Order.subscription_reference_id == subscription.subscription_id,
            Order.order_date >= from_date,
            Order.status == "scheduled",
        )
        .with_for_update()
        .all()
    )

    cancelled = 0
    refunded = ZERO
    for meal in meals:
        if not is_before_cutoff(meal.order_date, meal.meal_slot):
            continue
        meal.status = "cancelled"
        meal.cancel_reason = reason
        cancelled += 1
        if refund:
            refunded += refund_meal(
                db, meal, subscription,
                reason=refund_reason,
                description=f"Refund for cancelled {meal.meal_slot} on {meal.order_date}",
            )
        if meal.delivery_boy_reference_id:
            notify.delivery_partner(
                db, meal.delivery_boy_reference_id, "schedule_update", "Delivery cancelled",
                f"The {meal.meal_slot} delivery on {meal.order_date} was cancelled.",
                {"order_id": str(meal.order_id), "kind": "subscription"},
            )
    db.flush()
    return cancelled, refunded


# ── Settlement on delivery ────────────────────────────────────

def _legacy_partner_fee() -> Decimal:
    return money(DELIVERY_BOY_FEE_PER_DELIVERY)


def _book_platform(db: Session, settlement: dict, ref_type: str, ref_id, partner_payout: Decimal) -> None:
    for key, amount in (settlement.get("charges_per_delivery") or {}).items():
        entry_type = "commission" if key == "platform_commission" else key
        ledger.post_platform(
            db, entry_type=entry_type, direction="credit", amount=amount,
            reference_type=ref_type, reference_id=ref_id,
            idempotency_key=f"platform:{entry_type}:{ref_type}:{ref_id}",
        )
    discount = Decimal(settlement.get("plan_discount_per_delivery") or "0")
    ledger.post_platform(
        db, entry_type="plan_discount", direction="debit", amount=discount,
        reference_type=ref_type, reference_id=ref_id,
        idempotency_key=f"platform:plan_discount:{ref_type}:{ref_id}",
    )
    ledger.post_platform(
        db, entry_type="delivery_partner_payout", direction="debit", amount=partner_payout,
        reference_type=ref_type, reference_id=ref_id,
        idempotency_key=f"platform:delivery_partner_payout:{ref_type}:{ref_id}",
    )


def settle_subscription_meal(db: Session, order: Order) -> None:
    """Book kitchen, partner and platform money for a delivered meal (once)."""

    if order.settled_at is not None:
        return

    subscription = db.query(Subscription).filter(
        Subscription.subscription_id == order.subscription_reference_id
    ).first()
    settlement = ((subscription.pricing_snapshot or {}).get("settlement") if subscription else None) or {}

    if settlement:
        provider_amount = Decimal(settlement["provider_earning_per_delivery"])
        partner_amount = Decimal(settlement["partner_payout_per_delivery"])
    else:
        # Created before pricing snapshots: the rules in force at the time
        packages = db.query(SubscriptionPackage).filter(
            SubscriptionPackage.subscription_reference_id == order.subscription_reference_id
        ).all()
        provider_amount = sum((money(p.unit_price) * p.quantity for p in packages), ZERO)
        partner_amount = _legacy_partner_fee()

    if provider_amount > ZERO:
        ledger.post_provider(
            db, order.vendor_reference_id, type="credit", amount=provider_amount,
            reason="order_delivered", idempotency_key=f"earning:order:{order.order_id}",
            reference_type="order", reference_id=order.order_id,
            description=f"Earnings for {order.meal_slot} on {order.order_date}",
            counts_as_earning=True,
        )

    paid_partner = ZERO
    if order.delivery_boy_reference_id and partner_amount > ZERO:
        ledger.post_delivery(
            db, order.delivery_boy_reference_id, type="credit", amount=partner_amount,
            reason="delivery_payout", idempotency_key=f"payout:order:{order.order_id}",
            reference_type="order", reference_id=order.order_id,
            description=f"Delivery of {order.meal_slot} on {order.order_date}",
            counts_as_earning=True,
        )
        paid_partner = partner_amount
        notify.delivery_partner(
            db, order.delivery_boy_reference_id, "payout", "Delivery payout credited",
            f"Rs {partner_amount} added to your wallet.",
            {"reference_id": str(order.order_id), "reference_type": "order"},
        )

    if settlement:
        _book_platform(db, settlement, "order", order.order_id, paid_partner)
    elif paid_partner > ZERO:
        ledger.post_platform(
            db, entry_type="delivery_partner_payout", direction="debit", amount=paid_partner,
            reference_type="order", reference_id=order.order_id,
            idempotency_key=f"platform:delivery_partner_payout:order:{order.order_id}",
        )

    order.settled_at = now_utc()
    db.flush()


def settle_extra_order(db: Session, order: ExtraOrder) -> None:
    if order.settled_at is not None:
        return

    settlement = (order.pricing_snapshot or {}).get("settlement") or {}
    if settlement:
        provider_amount = Decimal(settlement["provider_earning_total"])
        partner_amount = Decimal(settlement["partner_payout_total"])
    else:
        provider_amount = money(order.total_price)
        partner_amount = _legacy_partner_fee()

    if provider_amount > ZERO:
        ledger.post_provider(
            db, order.vendor_reference_id, type="credit", amount=provider_amount,
            reason="order_delivered", idempotency_key=f"earning:extra_order:{order.extra_order_id}",
            reference_type="extra_order", reference_id=order.extra_order_id,
            description=f"Earnings for one-time {order.meal_slot} on {order.delivery_date}",
            counts_as_earning=True,
        )

    paid_partner = ZERO
    if order.delivery_boy_reference_id and partner_amount > ZERO:
        ledger.post_delivery(
            db, order.delivery_boy_reference_id, type="credit", amount=partner_amount,
            reason="delivery_payout", idempotency_key=f"payout:extra_order:{order.extra_order_id}",
            reference_type="extra_order", reference_id=order.extra_order_id,
            description=f"Delivery of one-time {order.meal_slot} on {order.delivery_date}",
            counts_as_earning=True,
        )
        paid_partner = partner_amount
        notify.delivery_partner(
            db, order.delivery_boy_reference_id, "payout", "Delivery payout credited",
            f"Rs {partner_amount} added to your wallet.",
            {"reference_id": str(order.extra_order_id), "reference_type": "extra_order"},
        )

    if settlement:
        # Extra orders are one delivery each: the full charges are booked
        full = dict(settlement)
        full["charges_per_delivery"] = {
            c["key"]: c["amount"] for c in (order.pricing_snapshot or {}).get("charges", [])
        }
        full["plan_discount_per_delivery"] = "0"
        _book_platform(db, full, "extra_order", order.extra_order_id, paid_partner)
    elif paid_partner > ZERO:
        ledger.post_platform(
            db, entry_type="delivery_partner_payout", direction="debit", amount=paid_partner,
            reference_type="extra_order", reference_id=order.extra_order_id,
            idempotency_key=f"platform:delivery_partner_payout:extra_order:{order.extra_order_id}",
        )

    order.settled_at = now_utc()
    db.flush()
