import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.delivery_boy_model import DeliveryBoy
from app.models.provider_model import Provider

# (mobile, name, vehicle_type, vehicle_number, assigned_provider_mobile)
DELIVERY_BOYS = [
    ("9123456701", "Ramesh Yadav",    "bike",    "MH01AB1234", "9876543201"),
    ("9123456702", "Suresh Gupta",    "scooter", "MH01CD5678", "9876543201"),
    ("9123456703", "Ravi Krishnan",   "bike",    "KA03EF9012", "9876543202"),
    ("9123456704", "Vijay Menon",     "scooter", "KA03GH3456", "9876543202"),
    ("9123456705", "Salim Sheikh",    "bike",    "TS09IJ7890", "9876543203"),
    ("9123456706", "Arjun Reddy",     "scooter", "TS09KL1234", "9876543203"),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        # Build provider_mobile → provider_id map
        provider_map = {}
        for mobile, _, _, _, p_mobile in DELIVERY_BOYS:
            if p_mobile not in provider_map:
                p = db.query(Provider).filter(Provider.mobile_number == p_mobile).first()
                if p:
                    provider_map[p_mobile] = p.provider_id
                else:
                    print(f"  ! Provider {p_mobile} not found — run providers_seeder.py first")

        for mobile, full_name, vehicle_type, vehicle_number, p_mobile in DELIVERY_BOYS:
            exists = db.query(DeliveryBoy).filter(DeliveryBoy.mobile_number == mobile).first()
            if exists:
                skipped += 1
                continue

            provider_id = provider_map.get(p_mobile)
            db.add(DeliveryBoy(
                mobile_number=mobile,
                hashed_password=hash_password("Delivery@1234"),
                full_name=full_name,
                is_mobile_verified=True,
                is_active=True,
                vehicle_type=vehicle_type,
                vehicle_number=vehicle_number,
                assigned_provider_reference_id=provider_id,
            ))
            inserted += 1
            print(f"  + {full_name} ({vehicle_type}) → provider {p_mobile}")

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
