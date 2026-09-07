import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.provider_model import Provider
from app.models.provider_wallet_model import ProviderWallet

# (mobile, balance, total_earned, total_withdrawn)
WALLET_DATA = [
    ("9876543201", 45000.00, 50000.00, 5000.00),
    ("9876543202", 28000.00, 30000.00, 2000.00),
    ("9876543203", 37000.00, 40000.00, 3000.00),
    ("9876543204", 19000.00, 20000.00, 1000.00),
    ("9876543205", 23000.00, 25000.00, 2000.00),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        for mobile, balance, total_earned, total_withdrawn in WALLET_DATA:
            provider = db.query(Provider).filter(Provider.mobile_number == mobile).first()
            if not provider:
                print(f"  ! Provider {mobile} not found — run providers_seeder.py first")
                continue

            exists = (
                db.query(ProviderWallet)
                .filter(ProviderWallet.provider_reference_id == provider.provider_id)
                .first()
            )
            if exists:
                skipped += 1
                continue

            db.add(ProviderWallet(
                provider_reference_id=provider.provider_id,
                balance=balance,
                total_earned=total_earned,
                total_withdrawn=total_withdrawn,
            ))
            inserted += 1
            print(f"  + {provider.business_name} — ₹{balance:.2f}")

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
