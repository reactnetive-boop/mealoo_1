"""
Seeds menu_packages, menu_package_items, menu_package_images,
and provider_selected_packages in one pass.
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.menu_category_model import MenuCategory
from app.models.menu_package_model import MenuPackage
from app.models.menu_package_item_model import MenuPackageItem
from app.models.menu_package_image_model import MenuPackageImage
from app.models.provider_model import Provider
from app.models.provider_selected_package_model import ProviderSelectedPackage

# fmt: (provider_mobile, category_slug, package_name, short_desc, meal_type, food_type,
#        price, discounted_price, sub_price, is_sub_available, items, capacity)
PACKAGES = [
    # ── Sharma Ji's Kitchen (Mumbai, North Indian) ──────────────────────────
    (
        "9876543201", "north-indian",
        "Dal Makhani Thali",
        "Creamy dal makhani with 4 rotis, rice, salad & pickle",
        "lunch", "veg", 180.00, 160.00, 150.00, True,
        ["Dal Makhani (300ml)", "4 Tandoor Rotis", "Steamed Rice (200g)", "Green Salad", "Pickle & Papad"],
        50,
    ),
    (
        "9876543201", "north-indian",
        "Paneer Butter Masala Combo",
        "Rich paneer butter masala with naan & sweet lassi",
        "dinner", "veg", 220.00, 200.00, 190.00, True,
        ["Paneer Butter Masala (250g)", "2 Butter Naan", "Steamed Rice (200g)", "Sweet Lassi (250ml)"],
        40,
    ),
    (
        "9876543201", "breakfast-specials",
        "Punjabi Breakfast Box",
        "Aloo paratha with white butter, curd & pickle",
        "breakfast", "veg", 120.00, 110.00, 100.00, True,
        ["2 Aloo Parathas", "White Butter (30g)", "Fresh Curd (150ml)", "Mixed Pickle"],
        60,
    ),
    (
        "9876543201", "non-vegetarian",
        "Chicken Curry Thali",
        "Dhaba-style chicken curry with rotis, rice & raita",
        "lunch", "non_veg", 280.00, 260.00, 250.00, True,
        ["Dhaba Chicken Curry (300g)", "4 Rotis", "Steamed Rice (250g)", "Onion Raita (150ml)", "Salad"],
        35,
    ),
    # ── Kerala Kitchen (Bengaluru, South Indian) ─────────────────────────────
    (
        "9876543202", "south-indian",
        "Kerala Sadya Combo",
        "Traditional Kerala sadya with avial, sambar, rice & payasam",
        "lunch", "veg", 200.00, 180.00, 170.00, True,
        ["Steamed Rice (300g)", "Sambar (200ml)", "Avial (150g)", "Thoran", "Papadam", "Payasam (150ml)"],
        45,
    ),
    (
        "9876543202", "south-indian",
        "Fish Curry Thali",
        "Kerala fish curry with appam & steamed rice",
        "dinner", "non_veg", 260.00, 240.00, 230.00, True,
        ["Kerala Fish Curry (250g)", "3 Appam", "Steamed Rice (200g)", "Coconut Chutney"],
        30,
    ),
    (
        "9876543202", "breakfast-specials",
        "South Indian Breakfast Plate",
        "Idli, vada, dosa with chutneys & sambar",
        "breakfast", "veg", 110.00, 100.00, 90.00, True,
        ["3 Idli", "1 Medu Vada", "1 Plain Dosa", "Coconut Chutney", "Tomato Chutney", "Sambar (200ml)"],
        70,
    ),
    # ── Spice Route Biryani (Hyderabad) ──────────────────────────────────────
    (
        "9876543203", "non-vegetarian",
        "Hyderabadi Chicken Dum Biryani",
        "Authentic Hyderabadi dum biryani with raita & salan",
        "lunch", "non_veg", 320.00, 290.00, 280.00, True,
        ["Chicken Dum Biryani (400g)", "Mirchi Ka Salan (150ml)", "Raita (150ml)", "Hard-boiled Egg"],
        40,
    ),
    (
        "9876543203", "non-vegetarian",
        "Mutton Biryani Box",
        "Slow-cooked mutton biryani with special shorba",
        "dinner", "non_veg", 400.00, 370.00, 360.00, True,
        ["Mutton Dum Biryani (400g)", "Shorba (200ml)", "Raita (150ml)", "Salad"],
        25,
    ),
    (
        "9876543203", "non-vegetarian",
        "Veg Biryani + Paneer Tikka",
        "Fragrant veg biryani with paneer tikka & raita",
        "lunch", "veg", 240.00, 220.00, 210.00, True,
        ["Veg Dum Biryani (350g)", "Paneer Tikka (150g)", "Raita (150ml)", "Gulab Jamun (2 pcs)"],
        50,
    ),
    # ── Patel Tiffin Service (Pune, Vegetarian) ──────────────────────────────
    (
        "9876543204", "vegetarian",
        "Gujarati Tiffin Box",
        "Home-style Gujarati thali with 5 items, roti & rice",
        "lunch", "veg", 160.00, 145.00, 140.00, True,
        ["Sabzi of the Day (200g)", "Dal Tadka (200ml)", "3 Phulkas", "Steamed Rice (200g)", "Chaas (200ml)"],
        80,
    ),
    (
        "9876543204", "breakfast-specials",
        "Upma & Poha Combo",
        "Light vegetarian breakfast with upma, poha & chai",
        "breakfast", "veg", 90.00, 80.00, 75.00, True,
        ["Upma (200g)", "Kanda Poha (200g)", "Masala Chai (200ml)"],
        100,
    ),
    (
        "9876543204", "healthy-fit",
        "Protein Fit Box",
        "High-protein meal with sprouts, grilled tofu & quinoa",
        "lunch", "veg", 210.00, 195.00, 185.00, True,
        ["Sprouted Salad (200g)", "Grilled Tofu (150g)", "Quinoa Pulao (200g)", "Buttermilk (200ml)"],
        45,
    ),
    # ── Chennai Samayal (Chennai, South Indian) ──────────────────────────────
    (
        "9876543205", "south-indian",
        "Chettinad Chicken Thali",
        "Spicy Chettinad chicken with rice, rasam & poriyal",
        "lunch", "non_veg", 290.00, 265.00, 255.00, True,
        ["Chettinad Chicken Curry (250g)", "Steamed Rice (300g)", "Rasam (200ml)", "Poriyal (150g)", "Papadam"],
        35,
    ),
    (
        "9876543205", "south-indian",
        "Sambar Rice Comfort Meal",
        "Classic Tamil sambar rice with kootu & curd rice",
        "dinner", "veg", 150.00, 135.00, 130.00, True,
        ["Sambar Rice (300g)", "Keerai Kootu (150g)", "Curd Rice (200g)", "Pickle & Papadam"],
        60,
    ),
    (
        "9876543205", "breakfast-specials",
        "Pongal & Vada Combo",
        "Ven pongal with ghee, medu vada & filter coffee",
        "breakfast", "veg", 100.00, 90.00, 85.00, True,
        ["Ven Pongal (250g)", "2 Medu Vada", "Coconut Chutney", "Filter Coffee (200ml)"],
        70,
    ),
]


def seed():
    db = SessionLocal()
    try:
        pkg_inserted = 0
        pkg_skipped = 0
        sel_inserted = 0
        sel_skipped = 0

        # Build lookup maps
        provider_map = {
            p.mobile_number: p
            for p in db.query(Provider).all()
        }
        category_map = {
            c.category_slug: c
            for c in db.query(MenuCategory).all()
        }

        for row in PACKAGES:
            (
                p_mobile, cat_slug, pkg_name, short_desc,
                meal_type, food_type, price, disc_price, sub_price,
                is_sub, items, capacity,
            ) = row

            provider = provider_map.get(p_mobile)
            if not provider:
                print(f"  ! Provider {p_mobile} not found — run providers_seeder.py first")
                continue

            category = category_map.get(cat_slug)
            if not category:
                print(f"  ! Category '{cat_slug}' not found — run menu_categories_seeder.py first")
                continue

            # Check package by name + provider
            existing_pkg = (
                db.query(MenuPackage)
                .filter(
                    MenuPackage.package_name == pkg_name,
                    MenuPackage.provider_id == provider.provider_id,
                )
                .first()
            )
            if existing_pkg:
                pkg_skipped += 1
                pkg = existing_pkg
            else:
                pkg = MenuPackage(
                    provider_id=provider.provider_id,
                    category_reference_id=category.category_id,
                    package_name=pkg_name,
                    short_description=short_desc,
                    meal_type=meal_type,
                    food_type=food_type,
                    price=price,
                    discounted_price=disc_price,
                    subscription_price=sub_price,
                    is_subscription_available=is_sub,
                    is_available=True,
                    is_active=True,
                )
                db.add(pkg)
                db.flush()  # get pkg.package_id

                # Insert items
                for order_idx, item_name in enumerate(items, start=1):
                    parts = item_name.rsplit("(", 1)
                    name_part = parts[0].strip()
                    qty_part = f"({parts[1]}" if len(parts) > 1 else ""
                    db.add(MenuPackageItem(
                        package_reference_id=pkg.package_id,
                        item_name=name_part,
                        quantity=qty_part,
                        item_order=order_idx,
                    ))

                # Insert a placeholder image
                db.add(MenuPackageImage(
                    package_reference_id=pkg.package_id,
                    image_url=f"https://cdn.mealoo.in/packages/{pkg_name.lower().replace(' ', '-')}.jpg",
                    is_primary=True,
                    display_order=1,
                ))

                pkg_inserted += 1
                print(f"  + Package: {pkg_name} ({provider.business_name})")

            # Provider selected package
            existing_sel = (
                db.query(ProviderSelectedPackage)
                .filter(
                    ProviderSelectedPackage.provider_id == provider.provider_id,
                    ProviderSelectedPackage.package_id == pkg.package_id,
                )
                .first()
            )
            if existing_sel:
                sel_skipped += 1
            else:
                db.add(ProviderSelectedPackage(
                    provider_id=provider.provider_id,
                    package_id=pkg.package_id,
                    is_active=True,
                    daily_capacity=capacity,
                ))
                sel_inserted += 1

        db.commit()
        print(f"\nPackages — Inserted: {pkg_inserted}, Skipped: {pkg_skipped}")
        print(f"Provider selections — Inserted: {sel_inserted}, Skipped: {sel_skipped}")

    except Exception as e:
        db.rollback()
        print(f"Seeding failed: {e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()
