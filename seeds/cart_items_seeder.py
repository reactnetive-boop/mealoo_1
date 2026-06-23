"""
Seeds cart items for testing the cart API.
Requires: users, providers, menu_packages seeders.
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user_model import User
from app.models.provider_model import Provider
from app.models.menu_package_model import MenuPackage
from app.models.cart_model import CartItem

# (user_phone, provider_mobile, package_name, quantity)
CART_ITEMS = [
    ("9000000008", "9876543201", "Dal Makhani Thali",              2),
    ("9000000008", "9876543201", "Punjabi Breakfast Box",          1),
    ("9000000009", "9876543203", "Hyderabadi Chicken Dum Biryani", 1),
    ("9000000010", "9876543205", "Chettinad Chicken Thali",        1),
    ("9000000010", "9876543205", "Pongal & Vada Combo",            2),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        for u_phone, p_mobile, pkg_name, qty in CART_ITEMS:
            user = db.query(User).filter(User.phone == u_phone).first()
            provider = db.query(Provider).filter(Provider.mobile_number == p_mobile).first()
            if not user or not provider:
                print(f"  ! Missing user {u_phone} or provider {p_mobile}")
                continue

            pkg = (
                db.query(MenuPackage)
                .filter(
                    MenuPackage.package_name == pkg_name,
                    MenuPackage.provider_id == provider.provider_id,
                )
                .first()
            )
            if not pkg:
                print(f"  ! Package '{pkg_name}' not found")
                continue

            exists = (
                db.query(CartItem)
                .filter(
                    CartItem.user_reference_id == user.user_id,
                    CartItem.package_reference_id == pkg.package_id,
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            db.add(CartItem(
                user_reference_id=user.user_id,
                vendor_reference_id=provider.provider_id,
                package_reference_id=pkg.package_id,
                quantity=qty,
            ))
            inserted += 1
            print(f"  + {user.full_name} → {pkg_name} × {qty}")

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
