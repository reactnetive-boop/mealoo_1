"""
Seeds provider complaints against platform or delivery boys.
Requires: providers, delivery_boys seeders.
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.provider_model import Provider
from app.models.delivery_boy_model import DeliveryBoy
from app.models.provider_complaint_model import ProviderComplaint

# (provider_mobile, against, delivery_boy_mobile, status, subject, description)
COMPLAINTS = [
    (
        "9876543201", "delivery_boy", "9123456702", "open",
        "Delivery boy repeatedly late for pickups",
        "Suresh Gupta has been late for order pickup 3 times this week. Orders are ready on time but he arrives 20-30 minutes late causing complaints from customers. Please address this.",
    ),
    (
        "9876543203", "platform", None, "in_progress",
        "Incorrect commission deduction on 15th June",
        "On 15th June 2026, the platform deducted 18% commission instead of the agreed 15% on my wallet settlement. The excess deduction amounts to Rs 850. Please review and refund.",
    ),
    (
        "9876543202", "delivery_boy", "9123456703", "resolved",
        "Delivery boy refused to deliver to 6th floor",
        "Ravi Krishnan refused to take the order to the 6th floor customer in Koramangala stating the building had no lift. The customer later complained to me. This is not acceptable.",
    ),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        for row in COMPLAINTS:
            p_mobile, against, db_mobile, status, subject, description = row

            provider = db.query(Provider).filter(Provider.mobile_number == p_mobile).first()
            if not provider:
                continue

            delivery_boy_id = None
            if db_mobile:
                dboy = db.query(DeliveryBoy).filter(DeliveryBoy.mobile_number == db_mobile).first()
                if dboy:
                    delivery_boy_id = dboy.delivery_boy_id

            exists = (
                db.query(ProviderComplaint)
                .filter(
                    ProviderComplaint.provider_reference_id == provider.provider_id,
                    ProviderComplaint.subject == subject,
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            db.add(ProviderComplaint(
                provider_reference_id=provider.provider_id,
                against=against,
                delivery_boy_reference_id=delivery_boy_id,
                status=status,
                subject=subject,
                description=description,
            ))
            inserted += 1
            print(f"  + {provider.business_name} — '{subject[:50]}' ({status})")

        db.commit()
        print(f"\nDone. Inserted: {inserted}, Skipped: {skipped}")

    except Exception as e:
        db.rollback()
        print(f"Seeding failed: {e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()
