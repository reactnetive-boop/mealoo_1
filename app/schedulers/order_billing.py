import logging
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.order_model import Order
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction

logger = logging.getLogger(__name__)


def process_order_billing(meal_slot: str) -> None:
    """
    Runs at the scheduled time for each meal slot (breakfast 6 AM,
    lunch 9 AM, dinner 3 PM).

    For every active-subscription order today matching `meal_slot`:

    - status="skipped" + free skips remaining  → mark is_free_skip, bump
      free_skips_used, no wallet deduction.
    - status="skipped" + no free skips left    → deduct slot amount (paid skip).
    - status="scheduled"                        → deduct slot amount.

    Wallet deduction is skipped (and logged as a failure) when the wallet
    is missing or has insufficient balance; those orders are NOT changed.
    """
    db: Session = SessionLocal()
    today = date.today()

    logger.info("[billing:%s] starting for %s", meal_slot, today)

    try:
        # ── 1. Fetch today's billable orders + their subscriptions ─────────
        rows = (
            db.query(Order, Subscription)
            .join(Subscription, Order.subscription_reference_id == Subscription.subscription_id)
            .filter(
                Order.order_date == today,
                Order.meal_slot == meal_slot,
                Order.status.in_(["scheduled", "skipped"]),
                Subscription.status == "active",
            )
            .all()
        )

        if not rows:
            logger.info("[billing:%s] nothing to process for %s", meal_slot, today)
            return

        # ── 2. Batch-load packages keyed by subscription_id ───────────────
        sub_ids = list({sub.subscription_id for _, sub in rows})

        all_packages = (
            db.query(SubscriptionPackage)
            .filter(SubscriptionPackage.subscription_reference_id.in_(sub_ids))
            .all()
        )

        packages_by_sub: dict[str, list[SubscriptionPackage]] = {}
        for pkg in all_packages:
            packages_by_sub.setdefault(str(pkg.subscription_reference_id), []).append(pkg)

        # ── 3. Batch-load wallets keyed by user_id ────────────────────────
        user_ids = list({sub.user_reference_id for _, sub in rows})

        all_wallets = (
            db.query(Wallet)
            .filter(Wallet.user_reference_id.in_(user_ids))
            .all()
        )

        wallets_by_user: dict[str, Wallet] = {
            str(w.user_reference_id): w for w in all_wallets
        }

        # ── 4. Process each order ─────────────────────────────────────────
        deducted = 0
        free_skips = 0
        paid_skips = 0
        failures = 0

        for order, subscription in rows:

            sub_packages = packages_by_sub.get(str(subscription.subscription_id), [])

            if not sub_packages:
                logger.warning(
                    "[billing:%s] no packages for subscription %s — skipping order %s",
                    meal_slot, subscription.subscription_id, order.order_id,
                )
                failures += 1
                continue

            slot_amount = sum(
                Decimal(str(pkg.unit_price)) * pkg.quantity
                for pkg in sub_packages
            )

            # ── Skipped order ─────────────────────────────────────────────
            if order.status == "skipped":
                free_remaining = (
                    subscription.free_skips_total - subscription.free_skips_used
                )

                if free_remaining > 0:
                    # Consume one free skip — no charge
                    subscription.free_skips_used += 1
                    order.is_free_skip = True
                    free_skips += 1
                    logger.info(
                        "[billing:%s] order %s: free skip used (%d/%d)",
                        meal_slot, order.order_id,
                        subscription.free_skips_used,
                        subscription.free_skips_total,
                    )
                    continue

                # No free skips left — fall through to deduct
                paid_skips += 1
                logger.info(
                    "[billing:%s] order %s: skipped but no free skips remaining — charging %s",
                    meal_slot, order.order_id, slot_amount,
                )

            # ── Wallet deduction ──────────────────────────────────────────
            wallet = wallets_by_user.get(str(subscription.user_reference_id))

            if not wallet:
                logger.error(
                    "[billing:%s] wallet not found for user %s (order %s)",
                    meal_slot, subscription.user_reference_id, order.order_id,
                )
                failures += 1
                continue

            if Decimal(str(wallet.balance)) < slot_amount:
                logger.warning(
                    "[billing:%s] insufficient balance for order %s — "
                    "required: %s, available: %s",
                    meal_slot, order.order_id, slot_amount, wallet.balance,
                )
                failures += 1
                continue

            balance_before = Decimal(str(wallet.balance))
            wallet.balance = wallet.balance - slot_amount
            balance_after = Decimal(str(wallet.balance))

            txn = WalletTransaction(
                wallet_reference_id=wallet.wallet_id,
                user_reference_id=subscription.user_reference_id,
                type="debit",
                reason="order_placed",
                amount=slot_amount,
                balance_before=balance_before,
                balance_after=balance_after,
                reference_id=order.order_id,
                reference_type="order",
                description=(
                    f"{meal_slot.capitalize()} order — "
                    f"{today.strftime('%d %b %Y')}"
                ),
                created_by=subscription.user_reference_id,
            )
            db.add(txn)
            deducted += 1

        # ── 5. Commit everything atomically ───────────────────────────────
        db.commit()

        logger.info(
            "[billing:%s] done for %s — deducted=%d  free_skips=%d  "
            "paid_skips=%d  failures=%d",
            meal_slot, today, deducted, free_skips, paid_skips, failures,
        )

    except Exception:
        db.rollback()
        logger.exception("[billing:%s] billing run failed — rolled back", meal_slot)

    finally:
        db.close()
