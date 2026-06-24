import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.subscription_model import Subscription
from app.models.order_model import Order
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction

logger = logging.getLogger(__name__)

# How many individual meal slots are in each subscription meal_slot value
SLOTS_PER_DAY = {
    "breakfast":        1,
    "lunch":            1,
    "dinner":           1,
    "breakfast_lunch":  2,
    "lunch_dinner":     2,
    "breakfast_dinner": 2,
    "all_slots":        3,
}


def _per_meal_refund(subscription: Subscription) -> Decimal:
    """
    Amount to refund when the user free-skips a single meal slot.

    refund = final_amount / (duration_days * slots_per_day)

    e.g. lunch+dinner plan, 30 days, final_amount=1800
         slots_per_day = 2
         per_meal = 1800 / (30 * 2) = 30 per meal slot
    """
    slots = SLOTS_PER_DAY.get(subscription.meal_slot, 1)
    duration = (subscription.end_date - subscription.start_date).days or 1
    divisor = Decimal(str(duration * slots))
    return (Decimal(str(subscription.final_amount)) / divisor).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def process_order_billing(meal_slot: str) -> None:
    """
    Runs at the scheduled time for each meal slot (breakfast 6 AM,
    lunch 9 AM, dinner 3 PM).

    Subscription amount is charged UPFRONT at subscription creation —
    this scheduler only handles SKIP REFUNDS.

    Rules:
    - status="scheduled"  → nothing (already paid upfront)
    - status="skipped" + free skips remaining
        → mark is_free_skip, bump free_skips_used,
          CREDIT back per-meal refund to user wallet
    - status="skipped" + NO free skips left
        → no refund (paid skip, amount already deducted upfront)
    """
    db: Session = SessionLocal()
    today = date.today()

    logger.info("[billing:%s] starting skip-refund run for %s", meal_slot, today)

    try:
        # ── 1. Fetch today's skipped orders + their active subscriptions ───
        rows = (
            db.query(Order, Subscription)
            .join(Subscription, Order.subscription_reference_id == Subscription.subscription_id)
            .filter(
                Order.order_date == today,
                Order.meal_slot == meal_slot,
                Order.status == "skipped",
                Subscription.status == "active",
            )
            .all()
        )

        if not rows:
            logger.info("[billing:%s] no skipped orders for %s", meal_slot, today)
            return

        # ── 2. Batch-load wallets keyed by user_id ────────────────────────
        user_ids = list({sub.user_reference_id for _, sub in rows})

        all_wallets = (
            db.query(Wallet)
            .filter(Wallet.user_reference_id.in_(user_ids))
            .all()
        )

        wallets_by_user: dict[str, Wallet] = {
            str(w.user_reference_id): w for w in all_wallets
        }

        # ── 3. Process each skipped order ─────────────────────────────────
        free_skip_refunds = 0
        paid_skips = 0
        failures = 0

        for order, subscription in rows:

            free_remaining = (
                subscription.free_skips_total - subscription.free_skips_used
            )

            if free_remaining <= 0:
                # No free skips left — paid skip, no refund
                paid_skips += 1
                logger.info(
                    "[billing:%s] order %s: paid skip (no free skips remaining)",
                    meal_slot, order.order_id,
                )
                continue

            # Free skip — refund the per-meal amount
            wallet = wallets_by_user.get(str(subscription.user_reference_id))

            if not wallet:
                logger.error(
                    "[billing:%s] wallet not found for user %s (order %s)",
                    meal_slot, subscription.user_reference_id, order.order_id,
                )
                failures += 1
                continue

            refund_amount = _per_meal_refund(subscription)
            balance_before = Decimal(str(wallet.balance))
            wallet.balance = wallet.balance + refund_amount
            balance_after = Decimal(str(wallet.balance))

            txn = WalletTransaction(
                wallet_reference_id=wallet.wallet_id,
                user_reference_id=subscription.user_reference_id,
                type="credit",
                reason="skip_refund",
                amount=refund_amount,
                balance_before=balance_before,
                balance_after=balance_after,
                reference_id=order.order_id,
                reference_type="order",
                description=(
                    f"Skip refund — {meal_slot.capitalize()} "
                    f"{today.strftime('%d %b %Y')} "
                    f"(free skip {subscription.free_skips_used + 1}"
                    f"/{subscription.free_skips_total})"
                ),
                created_by=subscription.user_reference_id,
            )
            db.add(txn)

            subscription.free_skips_used += 1
            order.is_free_skip = True
            free_skip_refunds += 1

            logger.info(
                "[billing:%s] order %s: free skip refund ₹%s credited "
                "(%d/%d skips used)",
                meal_slot, order.order_id, refund_amount,
                subscription.free_skips_used, subscription.free_skips_total,
            )

        # ── 4. Commit everything atomically ───────────────────────────────
        db.commit()

        logger.info(
            "[billing:%s] done for %s — free_skip_refunds=%d  "
            "paid_skips=%d  failures=%d",
            meal_slot, today, free_skip_refunds, paid_skips, failures,
        )

    except Exception:
        db.rollback()
        logger.exception("[billing:%s] billing run failed — rolled back", meal_slot)

    finally:
        db.close()
