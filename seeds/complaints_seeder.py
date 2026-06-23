"""
Seeds user complaints against vendors and platform.
Requires: users, providers seeders.
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user_model import User
from app.models.provider_model import Provider
from app.models.complaint_model import Complaint

# (user_phone, provider_mobile, against, status, subject, description)
COMPLAINTS = [
    (
        "9000000003", "9876543203", "vendor", "resolved",
        "Biryani was cold on arrival",
        "I received my Hyderabadi Chicken Dum Biryani completely cold even though I live nearby. The packaging seemed fine so it must have sat for too long before dispatch. Please ensure timely dispatch.",
    ),
    (
        "9000000005", "9876543202", "delivery", "open",
        "Delivery boy was rude",
        "The delivery person was very rude when I asked about the delay. He was about 40 minutes late and when I called him he was dismissive. This is not acceptable service behaviour.",
    ),
    (
        "9000000007", "9876543203", "vendor", "in_progress",
        "Wrong order delivered",
        "I had ordered the Mutton Biryani but received the Veg Biryani instead. When I contacted the vendor they said it was a mistake but offered no compensation. I would like a refund or replacement.",
    ),
    (
        "9000000008", None, "platform", "open",
        "Wallet top-up not reflecting",
        "I did a UPI payment of Rs 500 to top up my wallet 2 days ago. The money was debited from my account but the wallet balance has not been updated. Transaction reference: UPI20260621001234.",
    ),
    (
        "9000000002", "9876543202", "package", "resolved",
        "Food quality has deteriorated",
        "The South Indian Breakfast Plate quality has gone down over the past week. The idlis have been hard and the sambar is not as flavourful as before. Please look into this.",
    ),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        for row in COMPLAINTS:
            u_phone, p_mobile, against, status, subject, description = row

            user = db.query(User).filter(User.phone == u_phone).first()
            if not user:
                continue

            provider_id = None
            if p_mobile:
                provider = db.query(Provider).filter(Provider.mobile_number == p_mobile).first()
                if provider:
                    provider_id = provider.provider_id

            exists = (
                db.query(Complaint)
                .filter(
                    Complaint.user_reference_id == user.user_id,
                    Complaint.subject == subject,
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            db.add(Complaint(
                user_reference_id=user.user_id,
                vendor_reference_id=provider_id,
                against=against,
                status=status,
                subject=subject,
                description=description,
            ))
            inserted += 1
            print(f"  + {user.full_name} — '{subject[:50]}...' ({status})")

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
