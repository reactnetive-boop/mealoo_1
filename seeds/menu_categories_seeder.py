import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.menu_category_model import MenuCategory

# (display_order, category_name, category_slug, description)
CATEGORIES = [
    (1,  "North Indian",       "north-indian",       "Rich, aromatic curries, dals, and breads from Northern India"),
    (2,  "South Indian",       "south-indian",       "Dosas, idlis, sambars, and rice-based dishes from Southern India"),
    (3,  "Chinese",            "chinese",            "Indo-Chinese stir-fries, noodles, and fried rice"),
    (4,  "Continental",        "continental",        "Western-style salads, pastas, and grilled dishes"),
    (5,  "Street Food",        "street-food",        "Popular Indian street snacks and fast food"),
    (6,  "Healthy & Fit",      "healthy-fit",        "Nutritious, calorie-conscious meals for a healthy lifestyle"),
    (7,  "Vegetarian",         "vegetarian",         "100% vegetarian meals across all cuisines"),
    (8,  "Non-Vegetarian",     "non-vegetarian",     "Chicken, mutton, fish, and egg-based dishes"),
    (9,  "Breakfast Specials", "breakfast-specials", "Morning meals including poha, upma, parathas, and eggs"),
    (10, "Desserts & Sweets",  "desserts-sweets",    "Traditional Indian sweets and desserts"),
]


def seed():
    db = SessionLocal()

    try:
        inserted = 0
        skipped = 0

        for display_order, category_name, category_slug, description in CATEGORIES:
            exists = (
                db.query(MenuCategory)
                .filter(MenuCategory.category_slug == category_slug)
                .first()
            )

            if exists:
                skipped += 1
                continue

            db.add(
                MenuCategory(
                    category_name=category_name,
                    category_slug=category_slug,
                    description=description,
                    display_order=display_order,
                    is_active=True,
                )
            )
            inserted += 1
            print(f"  + Inserted category: {category_name} ({category_slug})")

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
