import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.provider_model import Provider, MealServiceType
from app.core.security import hash_password

PROVIDERS = [
    {
        "mobile_number":        "9876543201",
        "password":             "Provider@1234",
        "full_name":            "Rajesh Sharma",
        "business_name":        "Sharma Ji's Kitchen",
        "city":                 "Mumbai",
        "area":                 "Andheri West",
        "address":              "Shop 12, Andheri Market, Andheri West",
        "house_no":             "12",
        "landmark":             "Near Andheri Station",
        "state":                "Maharashtra",
        "pincode":              400001,
        "kitchen_type":         "Home Kitchen",
        "meal_service_type":    MealServiceType.FULL_DAY,
        "is_mobile_verified":   True,
        "is_active":            True,
        "is_profile_completed": True,
        "is_accepting_orders":  True,
    },
    {
        "mobile_number":        "9876543202",
        "password":             "Provider@1234",
        "full_name":            "Priya Nair",
        "business_name":        "Kerala Kitchen",
        "city":                 "Bengaluru",
        "area":                 "Koramangala",
        "address":              "15, 5th Block, Koramangala",
        "house_no":             "15",
        "landmark":             "Near Forum Mall",
        "state":                "Karnataka",
        "pincode":              560001,
        "kitchen_type":         "Cloud Kitchen",
        "meal_service_type":    MealServiceType.LUNCH_AND_DINNER,
        "is_mobile_verified":   True,
        "is_active":            True,
        "is_profile_completed": True,
        "is_accepting_orders":  True,
    },
    {
        "mobile_number":        "9876543203",
        "password":             "Provider@1234",
        "full_name":            "Mohammed Rafi Khan",
        "business_name":        "Spice Route Biryani",
        "city":                 "Hyderabad",
        "area":                 "Jubilee Hills",
        "address":              "Plot 34, Road No. 10, Jubilee Hills",
        "house_no":             "34",
        "landmark":             "Near Jubilee Hills Checkpost",
        "state":                "Telangana",
        "pincode":              500001,
        "kitchen_type":         "Restaurant Kitchen",
        "meal_service_type":    MealServiceType.LUNCH_AND_DINNER,
        "is_mobile_verified":   True,
        "is_active":            True,
        "is_profile_completed": True,
        "is_accepting_orders":  True,
    },
    {
        "mobile_number":        "9876543204",
        "password":             "Provider@1234",
        "full_name":            "Sunita Patel",
        "business_name":        "Patel Tiffin Service",
        "city":                 "Pune",
        "area":                 "Kothrud",
        "address":              "B-7, Shivneri Housing Society, Kothrud",
        "house_no":             "B-7",
        "landmark":             "Near Kothrud Bus Stand",
        "state":                "Maharashtra",
        "pincode":              411001,
        "kitchen_type":         "Home Kitchen",
        "meal_service_type":    MealServiceType.LUNCH_AND_BREAKFAST,
        "is_mobile_verified":   True,
        "is_active":            True,
        "is_profile_completed": True,
        "is_accepting_orders":  True,
    },
    {
        "mobile_number":        "9876543205",
        "password":             "Provider@1234",
        "full_name":            "Anand Kumar",
        "business_name":        "Chennai Samayal",
        "city":                 "Chennai",
        "area":                 "T. Nagar",
        "address":              "23, Usman Road, T. Nagar",
        "house_no":             "23",
        "landmark":             "Near Pondy Bazaar",
        "state":                "Tamil Nadu",
        "pincode":              600001,
        "kitchen_type":         "Cloud Kitchen",
        "meal_service_type":    MealServiceType.FULL_DAY,
        "is_mobile_verified":   True,
        "is_active":            True,
        "is_profile_completed": True,
        "is_accepting_orders":  True,
    },
]


def seed():
    db = SessionLocal()

    try:
        inserted = 0
        skipped = 0

        for p in PROVIDERS:
            exists = (
                db.query(Provider)
                .filter(Provider.mobile_number == p["mobile_number"])
                .first()
            )

            if exists:
                skipped += 1
                continue

            db.add(
                Provider(
                    mobile_number=p["mobile_number"],
                    hashed_password=hash_password(p["password"]),
                    full_name=p["full_name"],
                    business_name=p["business_name"],
                    city=p["city"],
                    area=p["area"],
                    address=p["address"],
                    house_no=p["house_no"],
                    landmark=p["landmark"],
                    state=p["state"],
                    pincode=p["pincode"],
                    kitchen_type=p["kitchen_type"],
                    meal_service_type=p["meal_service_type"],
                    is_mobile_verified=p["is_mobile_verified"],
                    is_active=p["is_active"],
                    is_profile_completed=p["is_profile_completed"],
                    is_accepting_orders=p["is_accepting_orders"],
                )
            )
            inserted += 1
            print(f"  + Inserted provider: {p['business_name']}")

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
