"""
Seeds daily subscription orders for active subscriptions.
Covers yesterday, today, and tomorrow with varied statuses.
Requires: subscriptions_seeder.
"""
import sys
import os
from datetime import date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.subscription_model import Subscription
from app.models.order_model import Order

TODAY = date.today()
DATES = [TODAY - timedelta(days=2), TODAY - timedelta(days=1), TODAY, TODAY + timedelta(days=1)]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        active_subs = (
            db.query(Subscription)
            .filter(Subscription.status == "active")
            .all()
        )

        for sub in active_subs:
            for order_date in DATES:
                # Skip if outside subscription window
                if order_date < sub.start_date or order_date > sub.end_date:
                    continue

                exists = (
                    db.query(Order)
                    .filter(
                        Order.subscription_reference_id == sub.subscription_id,
                        Order.order_date == order_date,
                        Order.meal_slot == sub.meal_slot,
                    )
                    .first()
                )
                if exists:
                    skipped += 1
                    continue

                if order_date < TODAY:
                    status = "delivered"
                elif order_date == TODAY:
                    status = "out_for_delivery"
                else:
                    status = "scheduled"

                db.add(Order(
                    subscription_reference_id=sub.subscription_id,
                    user_reference_id=sub.user_reference_id,
                    vendor_reference_id=sub.vendor_reference_id,
                    delivery_address_reference_id=sub.user_address_reference_id,
                    order_date=order_date,
                    meal_slot=sub.meal_slot,
                    status=status,
                    is_free_skip=False,
                ))
                inserted += 1

        db.commit()
        print(f"Orders seeded. Inserted: {inserted}, Skipped: {skipped}")

    except Exception as e:
        db.rollback()
        print(f"Seeding failed: {e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()
