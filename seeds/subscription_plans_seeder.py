import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.subscription_plan_model import SubscriptionPlan

MEAL_SLOTS = [
    "breakfast",
    "lunch",
    "dinner",
    "breakfast_lunch",
    "lunch_dinner",
    "breakfast_dinner",
    "all_slots",          # breakfast + lunch + dinner
]

# (subscription_type, duration_days, free_skips, discount_percent)
PLAN_DEFINITIONS = [
    ("weekly",      7,   1,  0.00),
    ("monthly",     30,  4,  5.00),
    ("quarterly",   90,  8,  10.00),
    ("half_yearly", 180, 12, 15.00),
    ("annually",    365, 24, 20.00),
    ("custom",      0,   0,  0.00),
]


def seed():
    db = SessionLocal()

    try:
        inserted = 0
        skipped = 0

        for sub_type, duration_days, free_skips, discount in PLAN_DEFINITIONS:
            for meal_slot in MEAL_SLOTS:

                exists = (
                    db.query(SubscriptionPlan)
                    .filter(
                        SubscriptionPlan.subscription_type == sub_type,
                        SubscriptionPlan.meal_slot == meal_slot
                    )
                    .first()
                )

                if exists:
                    skipped += 1
                    continue

                db.add(
                    SubscriptionPlan(
                        subscription_type=sub_type,
                        meal_slot=meal_slot,
                        duration_days=duration_days,
                        free_skips=free_skips,
                        discount_percent=discount,
                        is_active=True
                    )
                )
                inserted += 1
                print(f"  + [{sub_type}] {meal_slot} — {duration_days}d, {free_skips} skips, {discount}% off")

        db.commit()
        print(f"\nDone. Inserted: {inserted}, Skipped (already exist): {skipped}")

    except Exception as e:
        db.rollback()
        print(f"Seeding failed: {e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()
