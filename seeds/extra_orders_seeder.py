"""
Seeds extra (one-time) orders.
Requires: users, providers, user_addresses, menu_packages seeders.
"""
import sys
import os
from datetime import date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user_model import User
from app.models.provider_model import Provider
from app.models.user_address_model import UserAddress
from app.models.menu_package_model import MenuPackage
from app.models.extra_order_model import ExtraOrder

TODAY = date.today()

# (user_phone, provider_mobile, addr_label, package_name, qty, meal_slot, day_offset, status)
EXTRA_ORDERS = [
    ("9000000003", "9876543201", "Home", "Dal Makhani Thali",           1, "lunch",     -3, "delivered"),
    ("9000000004", "9876543203", "Home", "Hyderabadi Chicken Dum Biryani", 2, "lunch",  -2, "delivered"),
    ("9000000005", "9876543202", "Home", "Kerala Sadya Combo",           1, "lunch",    -1, "delivered"),
    ("9000000006", "9876543204", "Home", "Gujarati Tiffin Box",          1, "lunch",     0, "out_for_delivery"),
    ("9000000007", "9876543205", "Home", "Chettinad Chicken Thali",      1, "lunch",     0, "confirmed"),
    ("9000000008", "9876543201", "Home", "Paneer Butter Masala Combo",   1, "dinner",    1, "pending"),
    ("9000000009", "9876543202", "Home", "Fish Curry Thali",             1, "dinner",    1, "pending"),
    ("9000000010", "9876543203", "Home", "Mutton Biryani Box",           1, "dinner",    2, "pending"),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        for row in EXTRA_ORDERS:
            u_phone, p_mobile, addr_label, pkg_name, qty, meal_slot, day_offset, status = row

            user = db.query(User).filter(User.phone == u_phone).first()
            provider = db.query(Provider).filter(Provider.mobile_number == p_mobile).first()
            if not user or not provider:
                print(f"  ! Missing user {u_phone} or provider {p_mobile}")
                continue

            address = (
                db.query(UserAddress)
                .filter(
                    UserAddress.user_reference_id == user.user_id,
                    UserAddress.label == addr_label,
                )
                .first()
            )
            pkg = (
                db.query(MenuPackage)
                .filter(
                    MenuPackage.package_name == pkg_name,
                    MenuPackage.provider_id == provider.provider_id,
                )
                .first()
            )
            if not address or not pkg:
                print(f"  ! Missing address or package for user {u_phone}")
                continue

            delivery_date = TODAY + timedelta(days=day_offset)
            unit_price = pkg.discounted_price if pkg.discounted_price else pkg.price
            total_price = float(unit_price) * qty

            exists = (
                db.query(ExtraOrder)
                .filter(
                    ExtraOrder.user_reference_id == user.user_id,
                    ExtraOrder.package_reference_id == pkg.package_id,
                    ExtraOrder.delivery_date == delivery_date,
                    ExtraOrder.meal_slot == meal_slot,
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            db.add(ExtraOrder(
                user_reference_id=user.user_id,
                vendor_reference_id=provider.provider_id,
                address_reference_id=address.user_address_id,
                package_reference_id=pkg.package_id,
                quantity=qty,
                unit_price=unit_price,
                total_price=total_price,
                delivery_date=delivery_date,
                meal_slot=meal_slot,
                status=status,
            ))
            inserted += 1
            print(f"  + {user.full_name} → {pkg_name} ({meal_slot}, {delivery_date}, {status})")

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
