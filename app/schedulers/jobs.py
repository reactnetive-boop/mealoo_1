"""
Scheduled jobs. All are idempotent and safe to run on several instances at
once: each takes a Postgres advisory lock for its transaction, so a second
runner simply skips, and every money movement inside uses ledger idempotency
keys.

  generate_meals          daily 00:05 + at startup: create missing meals for
                          active subscriptions (never past dates / passed
                          cut-offs)
  expire_subscriptions    daily 00:01 + at startup: active subscriptions whose
                          end date has arrived become 'expired'
  cutoff_sweep            every 15 min: for every meal time whose cut-off has
                          passed today, cancel + refund meals of kitchens on
                          holiday that were not moved, and one-time orders
                          the kitchen never confirmed
  stale_sweep             daily 00:10 + at startup: anything from earlier days
                          still waiting (scheduled / pending / confirmed /
                          preparing) is cancelled and refunded; meals stuck
                          'out_for_delivery' are left for an admin
"""

import logging
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.audit import business_event
from app.core.clock import today_local
from app.core.config import STALE_SWEEP_LOOKBACK_DAYS
from app.core.database import SessionLocal
from app.domain import notify
from app.domain import orders as meals
from app.domain.slots import SLOTS, is_before_cutoff
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from app.models.provider_unavailability_model import ProviderUnavailability
from app.models.subscription_model import Subscription

logger = logging.getLogger("app.jobs")

# advisory lock ids (arbitrary, unique per job)
LOCK_GENERATE = 7_301
LOCK_EXPIRE = 7_302
LOCK_CUTOFF = 7_303
LOCK_STALE = 7_304


def _locked(db: Session, key: int) -> bool:
    return bool(db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": key}).scalar())


def _run(name: str, key: int, fn) -> None:
    db = SessionLocal()
    try:
        if not _locked(db, key):
            logger.info("[%s] another instance is running it; skipped", name)
            return
        result = fn(db)
        db.commit()
        logger.info("[%s] done %s", name, result)
    except Exception:
        db.rollback()
        logger.exception("[%s] failed; rolled back", name)
    finally:
        db.close()


# ── Generation ────────────────────────────────────────────────

def _generate(db: Session) -> dict:
    created = 0
    subs = db.query(Subscription).filter(Subscription.status == "active").all()
    for sub in subs:
        created += meals.generate_meals(db, sub, from_date=today_local())
    return {"subscriptions": len(subs), "meals_created": created}


def generate_meals_job() -> None:
    _run("generate_meals", LOCK_GENERATE, _generate)


# ── Expiry ────────────────────────────────────────────────────

def _expire(db: Session) -> dict:
    today = today_local()
    subs = (
        db.query(Subscription)
        .filter(Subscription.status == "active", Subscription.end_date <= today)
        .with_for_update(skip_locked=True)
        .all()
    )
    for sub in subs:
        sub.status = "expired"
        notify.customer(
            db, sub.user_reference_id, "subscription_expired", "Subscription completed",
            "Your subscription has ended. Renew it any time from the app.",
            {"subscription_id": str(sub.subscription_id)},
        )
    return {"expired": len(subs)}


def expire_subscriptions_job() -> None:
    _run("expire_subscriptions", LOCK_EXPIRE, _expire)


# ── Cut-off sweep (holidays, unconfirmed one-time orders) ────

def _cancel_meal(db: Session, order: Order, reason: str, message: str) -> None:
    sub = db.query(Subscription).filter(
        Subscription.subscription_id == order.subscription_reference_id
    ).with_for_update().first()
    order.status = "cancelled"
    order.cancel_reason = reason
    refunded = meals.refund_meal(
        db, order, sub, reason="order_cancel_refund",
        description=f"Refund for {order.meal_slot} on {order.order_date} ({reason.replace('_', ' ')})",
    )
    notify.customer(
        db, order.user_reference_id, "order_cancelled", "Meal cancelled",
        f"{message} Rs {refunded} refunded to your wallet.",
        {"order_id": str(order.order_id)},
    )
    if order.delivery_boy_reference_id:
        notify.delivery_partner(
            db, order.delivery_boy_reference_id, "schedule_update", "Delivery cancelled",
            f"The {order.meal_slot} delivery on {order.order_date} was cancelled.",
            {"order_id": str(order.order_id), "kind": "subscription"},
        )


def _cancel_extra(db: Session, order: ExtraOrder, reason: str, message: str) -> None:
    order.status = "cancelled"
    order.cancel_reason = reason
    refunded = meals.refund_extra_order(
        db, order, reason="order_cancel_refund",
        description=f"Refund for one-time order on {order.delivery_date} ({reason.replace('_', ' ')})",
    )
    notify.customer(
        db, order.user_reference_id, "order_cancelled", "Order cancelled",
        f"{message} Rs {refunded} refunded to your wallet.",
        {"extra_order_id": str(order.extra_order_id)},
    )


def _cutoff(db: Session) -> dict:
    today = today_local()
    passed = [s for s in SLOTS if not is_before_cutoff(today, s)]
    if not passed:
        return {"slots": []}

    holiday_kitchens = [
        r.provider_reference_id
        for r in db.query(ProviderUnavailability.provider_reference_id).filter(
            ProviderUnavailability.unavailable_date == today
        )
    ]

    holiday_meals = holiday_extras = unconfirmed = 0
    if holiday_kitchens:
        for order in (
            db.query(Order)
            .filter(
                Order.order_date == today,
                Order.meal_slot.in_(passed),
                Order.status == "scheduled",
                Order.vendor_reference_id.in_(holiday_kitchens),
            )
            .with_for_update(skip_locked=True)
        ):
            _cancel_meal(db, order, "kitchen_holiday", f"Your kitchen is closed today, so your {order.meal_slot} was cancelled.")
            holiday_meals += 1

        for order in (
            db.query(ExtraOrder)
            .filter(
                ExtraOrder.delivery_date == today,
                ExtraOrder.meal_slot.in_(passed),
                ExtraOrder.status.in_(("pending", "confirmed")),
                ExtraOrder.vendor_reference_id.in_(holiday_kitchens),
            )
            .with_for_update(skip_locked=True)
        ):
            _cancel_extra(db, order, "kitchen_holiday", "The kitchen is closed today, so your order was cancelled.")
            holiday_extras += 1

    for order in (
        db.query(ExtraOrder)
        .filter(
            ExtraOrder.delivery_date == today,
            ExtraOrder.meal_slot.in_(passed),
            ExtraOrder.status == "pending",
        )
        .with_for_update(skip_locked=True)
    ):
        _cancel_extra(db, order, "kitchen_not_confirmed", "The kitchen did not confirm your order in time.")
        unconfirmed += 1

    if holiday_meals or holiday_extras or unconfirmed:
        business_event(
            "jobs.cutoff_sweep", date=today, holiday_meals=holiday_meals,
            holiday_extra_orders=holiday_extras, unconfirmed_extra_orders=unconfirmed,
        )
    return {
        "slots": passed,
        "holiday_meals": holiday_meals,
        "holiday_extra_orders": holiday_extras,
        "unconfirmed_extra_orders": unconfirmed,
    }


def cutoff_sweep_job() -> None:
    _run("cutoff_sweep", LOCK_CUTOFF, _cutoff)


# ── Stale orders from earlier days ────────────────────────────

def _stale(db: Session) -> dict:
    today = today_local()
    # bounded look-back so a first run over old data cannot mass-refund history;
    # anything older is only reported for an admin to review
    since = today - timedelta(days=STALE_SWEEP_LOOKBACK_DAYS)
    stale_meals = stale_extras = 0
    for order in (
        db.query(Order)
        .filter(Order.order_date < today, Order.order_date >= since, Order.status.in_(("scheduled", "preparing")))
        .with_for_update(skip_locked=True)
    ):
        _cancel_meal(db, order, "not_fulfilled", f"Your {order.meal_slot} on {order.order_date} was not delivered.")
        stale_meals += 1

    for order in (
        db.query(ExtraOrder)
        .filter(
            ExtraOrder.delivery_date < today,
            ExtraOrder.delivery_date >= since,
            ExtraOrder.status.in_(("pending", "confirmed", "preparing")),
        )
        .with_for_update(skip_locked=True)
    ):
        _cancel_extra(db, order, "not_fulfilled", f"Your order for {order.delivery_date} was not delivered.")
        stale_extras += 1

    stuck = (
        db.query(Order).filter(Order.order_date < today, Order.status == "out_for_delivery").count()
        + db.query(ExtraOrder).filter(ExtraOrder.delivery_date < today, ExtraOrder.status == "out_for_delivery").count()
    )
    older = (
        db.query(Order).filter(Order.order_date < since, Order.status.in_(("scheduled", "preparing"))).count()
        + db.query(ExtraOrder).filter(
            ExtraOrder.delivery_date < since, ExtraOrder.status.in_(("pending", "confirmed", "preparing"))
        ).count()
    )
    if stuck or older:
        logger.warning(
            "[stale_sweep] admin review needed: %s still out for delivery, %s open beyond the %s-day look-back",
            stuck, older, STALE_SWEEP_LOOKBACK_DAYS,
        )
    return {
        "cancelled_meals": stale_meals,
        "cancelled_extra_orders": stale_extras,
        "stuck_out_for_delivery": stuck,
        "older_than_lookback": older,
    }


def stale_sweep_job() -> None:
    _run("stale_sweep", LOCK_STALE, _stale)


def startup_catch_up() -> None:
    expire_subscriptions_job()
    stale_sweep_job()
    generate_meals_job()
    cutoff_sweep_job()
