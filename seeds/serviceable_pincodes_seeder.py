import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.serviceable_pincode_model import ServiceablePincode

# (pincode, city, state)
PINCODES = [
    (400001, "Mumbai",      "Maharashtra"),
    (411001, "Pune",        "Maharashtra"),
    (560001, "Bengaluru",   "Karnataka"),
    (500001, "Hyderabad",   "Telangana"),
    (600001, "Chennai",     "Tamil Nadu"),
    (110001, "New Delhi",   "Delhi"),
    (380001, "Ahmedabad",   "Gujarat"),
    (302001, "Jaipur",      "Rajasthan"),
    (700001, "Kolkata",     "West Bengal"),
    (160001, "Chandigarh",  "Chandigarh"),
    (226001, "Lucknow",     "Uttar Pradesh"),
    (440001, "Nagpur",      "Maharashtra"),
]


def seed():
    db = SessionLocal()

    try:
        inserted = 0
        skipped = 0

        for pincode, city, state in PINCODES:
            exists = (
                db.query(ServiceablePincode)
                .filter(ServiceablePincode.pincode == pincode)
                .first()
            )

            if exists:
                skipped += 1
                continue

            db.add(
                ServiceablePincode(
                    pincode=pincode,
                    city=city,
                    state=state,
                    is_active=True,
                )
            )
            inserted += 1
            print(f"  + Inserted pincode: {pincode} ({city}, {state})")

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
