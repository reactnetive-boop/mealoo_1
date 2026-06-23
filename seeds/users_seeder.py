import sys
import os
import random
import string

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user_model import User

USERS = [
    ("9000000001", "aditya.singh@gmail.com",  "Aditya Singh",  "male"),
    ("9000000002", "meera.patel@gmail.com",   "Meera Patel",   "female"),
    ("9000000003", "rohit.kumar@yahoo.com",   "Rohit Kumar",   "male"),
    ("9000000004", "sneha.sharma@gmail.com",  "Sneha Sharma",  "female"),
    ("9000000005", "karan.mehta@hotmail.com", "Karan Mehta",   "male"),
    ("9000000006", "divya.reddy@gmail.com",   "Divya Reddy",   "female"),
    ("9000000007", "suresh.iyer@gmail.com",   "Suresh Iyer",   "male"),
    ("9000000008", "ananya.nair@gmail.com",   "Ananya Nair",   "female"),
    ("9000000009", "vikas.joshi@gmail.com",   "Vikas Joshi",   "male"),
    ("9000000010", "pooja.gupta@gmail.com",   "Pooja Gupta",   "female"),
]


def _generate_referral_code(db):
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not db.query(User).filter(User.referral_code == code).first():
            return code


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        for phone, email, full_name, gender in USERS:
            exists = db.query(User).filter(User.phone == phone).first()
            if exists:
                skipped += 1
                continue

            db.add(User(
                phone=phone,
                email=email,
                full_name=full_name,
                gender=gender,
                phone_verified=True,
                email_verified=True,
                password_hash=hash_password("User@1234"),
                is_profile_completed=True,
                status="active",
                referral_code=_generate_referral_code(db),
            ))
            inserted += 1
            print(f"  + {full_name} ({phone})")

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
