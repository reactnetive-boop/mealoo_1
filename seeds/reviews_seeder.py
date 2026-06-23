"""
Seeds user reviews for providers and packages.
Requires: users, providers, menu_packages seeders.
"""
import sys
import os
from datetime import date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user_model import User
from app.models.provider_model import Provider
from app.models.menu_package_model import MenuPackage
from app.models.review_model import Review

TODAY = date.today()

# (user_phone, provider_mobile, package_name, vendor_rating, pkg_rating, text, day_offset)
REVIEWS = [
    (
        "9000000001", "9876543201", "Dal Makhani Thali",
        5, 5,
        "Absolutely loved the Dal Makhani! Perfectly spiced and the rotis were fresh and soft. Delivery was on time too.",
        -3,
    ),
    (
        "9000000002", "9876543202", "South Indian Breakfast Plate",
        5, 4,
        "The idlis were fluffy and the sambar was very authentic. Reminds me of home. Will subscribe again!",
        -2,
    ),
    (
        "9000000003", "9876543203", "Hyderabadi Chicken Dum Biryani",
        4, 5,
        "Best Hyderabadi biryani I have had outside of Hyderabad. The dum process is clearly done right — aromatic and flavourful.",
        -2,
    ),
    (
        "9000000004", "9876543204", "Gujarati Tiffin Box",
        5, 4,
        "Sunita didi's tiffin is just like home-cooked food. The sabzi changes daily which is great. Highly recommend.",
        -1,
    ),
    (
        "9000000005", "9876543202", "Kerala Sadya Combo",
        4, 4,
        "Good spread of dishes. The avial and payasam were highlights. Would have been 5 stars if portions were bigger.",
        -1,
    ),
    (
        "9000000006", "9876543202", "Fish Curry Thali",
        5, 5,
        "Authentic Kerala fish curry with just the right amount of coconut milk. The appam was perfect.",
        -1,
    ),
    (
        "9000000007", "9876543203", "Mutton Biryani Box",
        3, 3,
        "The mutton was tender but the biryani was a bit under-spiced for my taste. The salan was good though.",
        -1,
    ),
    (
        "9000000008", "9876543201", "Paneer Butter Masala Combo",
        4, 4,
        "Good paneer butter masala, rich and creamy. The naan was a tad dry but overall a satisfying dinner.",
        -1,
    ),
    (
        "9000000009", "9876543205", "Sambar Rice Comfort Meal",
        5, 5,
        "This is exactly what I needed after a long day. Simple, homely, and delicious. The curd rice was a perfect finish.",
        -2,
    ),
    (
        "9000000010", "9876543205", "Pongal & Vada Combo",
        4, 5,
        "The pongal had the right amount of ghee and pepper. Vadas were crispy. Filter coffee was a nice touch.",
        -3,
    ),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        for row in REVIEWS:
            u_phone, p_mobile, pkg_name, v_rating, p_rating, text, day_offset = row

            user = db.query(User).filter(User.phone == u_phone).first()
            provider = db.query(Provider).filter(Provider.mobile_number == p_mobile).first()
            if not user or not provider:
                continue

            pkg = (
                db.query(MenuPackage)
                .filter(
                    MenuPackage.package_name == pkg_name,
                    MenuPackage.provider_id == provider.provider_id,
                )
                .first()
            )

            review_date = TODAY + timedelta(days=day_offset)

            exists = (
                db.query(Review)
                .filter(
                    Review.user_reference_id == user.user_id,
                    Review.vendor_reference_id == provider.provider_id,
                    Review.review_date == review_date,
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            db.add(Review(
                user_reference_id=user.user_id,
                vendor_reference_id=provider.provider_id,
                package_reference_id=pkg.package_id if pkg else None,
                vendor_rating=v_rating,
                package_rating=p_rating,
                review_text=text,
                review_date=review_date,
                is_visible=True,
            ))
            inserted += 1
            print(f"  + {user.full_name} → {provider.business_name} ({v_rating}★)")

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
