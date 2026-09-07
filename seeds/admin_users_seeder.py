import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.admin_user_model import AdminUser
from app.core.security import hash_password

ADMIN_USERS = [
    {
        "full_name": "Rahul Verma",
        "email": "rahul.admin@mealoo.in",
        "password": "Admin@1234",
        "role": "super_admin",
    },
    {
        "full_name": "Priya Sharma",
        "email": "priya.admin@mealoo.in",
        "password": "Admin@5678",
        "role": "moderator",
    },
]


def seed():
    db = SessionLocal()

    try:
        inserted = 0
        skipped = 0

        for user in ADMIN_USERS:
            exists = (
                db.query(AdminUser)
                .filter(AdminUser.email == user["email"])
                .first()
            )

            if exists:
                skipped += 1
                continue

            db.add(
                AdminUser(
                    full_name=user["full_name"],
                    email=user["email"],
                    password_hash=hash_password(user["password"]),
                    role=user["role"],
                    is_active=True,
                )
            )
            inserted += 1
            print(f"  + Inserted admin: {user['email']}")

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
