import uuid
import random
import logging

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.subscription_model import Subscription
from app.models.order_model import Order

logger = logging.getLogger(__name__)

# Maps subscription meal_slot → individual order meal slots
MEAL_SLOT_EXPANSION = {
    "breakfast":        ["breakfast"],
    "lunch":            ["lunch"],
    "dinner":           ["dinner"],
    "breakfast_lunch":  ["breakfast", "lunch"],
    "lunch_dinner":     ["lunch", "dinner"],
    "breakfast_dinner": ["breakfast", "dinner"],
    "all_slots":        ["breakfast", "lunch", "dinner"],
}


def _generate_otp() -> str:
    return str(random.randint(100000, 999999))


def generate_subscription_orders():
    """
    For every active subscription, create orders for every date in its
    period that does not already have an order. Safe to run repeatedly —
    already-existing (subscription_id, order_date, meal_slot) rows are
    skipped via a set-difference check before any insert.
    """
    db: Session = SessionLocal()

    try:
        # 1. Fetch all active subscriptions in one query
        active_subscriptions = (
            db.query(Subscription)
            .filter(Subscription.status == "active")
            .all()
        )

        if not active_subscriptions:
            logger.info("Order generator: no active subscriptions found.")
            return

        total_created = 0

        for sub in active_subscriptions:

            individual_slots = MEAL_SLOT_EXPANSION.get(
                sub.meal_slot, [sub.meal_slot]
            )

            # 2. Bulk-fetch existing (order_date, meal_slot) for this subscription
            existing_rows = (
                db.query(Order.order_date, Order.meal_slot)
                .filter(Order.subscription_reference_id == sub.subscription_id)
                .all()
            )

            existing_set = {(row.order_date, row.meal_slot) for row in existing_rows}

            # 3. Build all expected (date, slot) pairs for the subscription period
            new_orders = []
            current_date = sub.start_date

            while current_date < sub.end_date:

                for slot in individual_slots:

                    if (current_date, slot) not in existing_set:

                        new_orders.append({
                            "order_id": uuid.uuid4(),
                            "subscription_reference_id": sub.subscription_id,
                            "user_reference_id": sub.user_reference_id,
                            "vendor_reference_id": sub.vendor_reference_id,
                            "delivery_address_reference_id": sub.user_address_reference_id,
                            "order_date": current_date,
                            "meal_slot": slot,
                            "status": "scheduled",
                            "is_free_skip": False,
                            "otp_for_delivery": _generate_otp(),
                        })

                current_date += timedelta(days=1)

            # 4. Bulk insert missing orders
            if new_orders:
                db.bulk_insert_mappings(Order, new_orders)
                total_created += len(new_orders)
                logger.info(
                    f"Subscription {sub.subscription_id}: created {len(new_orders)} orders."
                )

        db.commit()
        logger.info(
            f"Order generator complete. Total orders created: {total_created}"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Order generator failed: {e}", exc_info=True)

    finally:
        db.close()
