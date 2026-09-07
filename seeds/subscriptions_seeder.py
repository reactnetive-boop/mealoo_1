"""
Seeds subscriptions + subscription_packages.
Requires: users, providers, user_addresses, subscription_plans, menu_packages seeders.
"""
import sys
import os
from datetime import date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user_model import User
from app.models.provider_model import Provider
from app.models.user_address_model import UserAddress
from app.models.subscription_plan_model import SubscriptionPlan
from app.models.menu_package_model import MenuPackage
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage

TODAY = date.today()

# (user_phone, provider_mobile, address_label, plan_type, plan_slot, meal_slot,
#  start_offset_days, status, package_names_with_qty)
SUBSCRIPTIONS = [
    (
        "9000000001", "9876543201", "Home",
        "monthly", "lunch", "lunch",
        -10, "active",
        [("Dal Makhani Thali", 1)],
    ),
    (
        "9000000002", "9876543202", "Home",
        "monthly", "breakfast", "breakfast",
        -5, "active",
        [("South Indian Breakfast Plate", 1)],
    ),
    (
        "9000000003", "9876543203", "Home",
        "weekly", "lunch", "lunch",
        -3, "active",
        [("Hyderabadi Chicken Dum Biryani", 1)],
    ),
    (
        "9000000004", "9876543204", "Home",
        "monthly", "lunch", "lunch",
        -15, "active",
        [("Gujarati Tiffin Box", 1)],
    ),
    (
        "9000000005", "9876543205", "Home",
        "weekly", "dinner", "dinner",
        -20, "expired",
        [("Sambar Rice Comfort Meal", 1)],
    ),
    (
        "9000000001", "9876543201", "Work",
        "weekly", "breakfast", "breakfast",
        -2, "active",
        [("Punjabi Breakfast Box", 1)],
    ),
    (
        "9000000006", "9876543202", "Home",
        "monthly", "dinner", "dinner",
        -8, "paused",
        [("Fish Curry Thali", 1)],
    ),
    (
        "9000000007", "9876543203", "Home",
        "monthly", "lunch", "lunch",
        -12, "cancelled",
        [("Mutton Biryani Box", 1)],
    ),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        for row in SUBSCRIPTIONS:
            (
                u_phone, p_mobile, addr_label,
                plan_type, plan_slot, meal_slot,
                start_offset, status, pkg_qty_list,
            ) = row

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
            if not address:
                print(f"  ! Address '{addr_label}' not found for user {u_phone}")
                continue

            plan = (
                db.query(SubscriptionPlan)
                .filter(
                    SubscriptionPlan.subscription_type == plan_type,
                    SubscriptionPlan.meal_slot == plan_slot,
                    SubscriptionPlan.is_active == True,
                )
                .first()
            )
            if not plan:
                print(f"  ! Plan ({plan_type}/{plan_slot}) not found — run subscription_plans_seeder.py first")
                continue

            # Resolve packages
            packages = []
            for pkg_name, qty in pkg_qty_list:
                pkg = (
                    db.query(MenuPackage)
                    .filter(
                        MenuPackage.package_name == pkg_name,
                        MenuPackage.provider_id == provider.provider_id,
                    )
                    .first()
                )
                if not pkg:
                    print(f"  ! Package '{pkg_name}' not found for provider {p_mobile}")
                    continue
                packages.append((pkg, qty))

            if not packages:
                continue

            start_date = TODAY + timedelta(days=start_offset)
            end_date = start_date + timedelta(days=plan.duration_days or 30)

            # Calculate totals
            total_amount = sum(
                (float(pkg.subscription_price or pkg.price)) * qty
                * (plan.duration_days or 30)
                for pkg, qty in packages
            )
            discount = float(plan.discount_percent or 0) / 100.0
            discount_amount = round(total_amount * discount, 2)
            final_amount = round(total_amount - discount_amount, 2)

            # Check duplicate: same user + provider + meal_slot + start_date
            exists = (
                db.query(Subscription)
                .filter(
                    Subscription.user_reference_id == user.user_id,
                    Subscription.vendor_reference_id == provider.provider_id,
                    Subscription.meal_slot == meal_slot,
                    Subscription.start_date == start_date,
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            sub = Subscription(
                user_reference_id=user.user_id,
                vendor_reference_id=provider.provider_id,
                plan_reference_id=plan.subscription_plan_id,
                user_address_reference_id=address.user_address_id,
                status=status,
                meal_slot=meal_slot,
                subscription_type=plan_type,
                start_date=start_date,
                end_date=end_date,
                free_skips_total=plan.free_skips or 0,
                free_skips_used=0,
                total_amount=total_amount,
                discount_amount=discount_amount,
                final_amount=max(final_amount, 1.0),
            )
            db.add(sub)
            db.flush()

            for pkg, qty in packages:
                unit_price = pkg.subscription_price or pkg.price
                db.add(SubscriptionPackage(
                    subscription_reference_id=sub.subscription_id,
                    package_reference_id=pkg.package_id,
                    quantity=qty,
                    unit_price=unit_price,
                ))

            inserted += 1
            print(f"  + {user.full_name} → {provider.business_name} ({meal_slot}, {status})")

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
