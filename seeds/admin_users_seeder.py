import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.admin_user_model import AdminUser
from app.core.security import hash_password

# Credentials come from the environment, never from source control:
#   ADMIN_SEED_EMAIL, ADMIN_SEED_PASSWORD (12+ chars), ADMIN_SEED_NAME,
#   ADMIN_SEED_ROLE (super_admin | moderator, default moderator)
def _admin_users():
    email = os.getenv("ADMIN_SEED_EMAIL")
    password = os.getenv("ADMIN_SEED_PASSWORD")
    if not email or not password:
        print("ADMIN_SEED_EMAIL / ADMIN_SEED_PASSWORD not set - no admin seeded.")
        return []
    if len(password) < 12:
        raise SystemExit("ADMIN_SEED_PASSWORD must be at least 12 characters")
    role = os.getenv("ADMIN_SEED_ROLE", "moderator")
    if role not in ("super_admin", "moderator"):
        raise SystemExit("ADMIN_SEED_ROLE must be super_admin or moderator")
    return [{
        "full_name": os.getenv("ADMIN_SEED_NAME", "Orleeno Admin"),
        "email": email.strip().lower(),
        "password": password,
        "role": role,
    }]


def seed():
    db = SessionLocal()

    try:
        inserted = 0
        skipped = 0

        for user in _admin_users():
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
