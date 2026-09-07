import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user_model import User
from app.models.wallet_model import Wallet

# (phone, initial_balance)
WALLET_BALANCES = [
    ("9000000001", 2000.00),
    ("9000000002", 2000.00),
    ("9000000003", 2000.00),
    ("9000000004", 2000.00),
    ("9000000005", 2000.00),
    ("9000000006", 1500.00),
    ("9000000007", 1500.00),
    ("9000000008", 1500.00),
    ("9000000009",  500.00),
    ("9000000010",  500.00),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        for phone, balance in WALLET_BALANCES:
            user = db.query(User).filter(User.phone == phone).first()
            if not user:
                print(f"  ! User {phone} not found — run users_seeder.py first")
                continue

            exists = db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).first()
            if exists:
                skipped += 1
                continue

            db.add(Wallet(
                user_reference_id=user.user_id,
                balance=balance,
            ))
            inserted += 1
            print(f"  + {user.full_name} ({phone}) — ₹{balance:.2f}")

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
