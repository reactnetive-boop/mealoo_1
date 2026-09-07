import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user_model import User
from app.models.user_address_model import UserAddress

# (phone, label, line1, line2, landmark, city, state, pin_code, lat, lng, is_default)
ADDRESS_DATA = [
    ("9000000001", "Home", "Flat 401, Sunrise Apartments, Andheri West", None,        "Near Andheri Station",    "Mumbai",       "Maharashtra", "400001", 19.119201, 72.846550, True),
    ("9000000001", "Work", "Floor 3, Techpark, Bandra Kurla Complex",    "BKC",       "Near BKC Metro",          "Mumbai",       "Maharashtra", "400051", 19.067320, 72.869750, False),
    ("9000000002", "Home", "102, Sahara Heights, Kothrud",               None,        "Near Kothrud Bus Stand",  "Pune",         "Maharashtra", "411001", 18.508445, 73.807770, True),
    ("9000000002", "Work", "Office Park, Phase 1, Hinjewadi",            None,        "Near Hinjewadi IT Park",  "Pune",         "Maharashtra", "411057", 18.592340, 73.737400, False),
    ("9000000003", "Home", "305, Green Valley Apts, 5th Block Koramangala", None,    "Near Forum Mall",          "Bengaluru",    "Karnataka",   "560001", 12.934938, 77.624290, True),
    ("9000000003", "Work", "Tech Tower B, Whitefield Main Road",         None,        "Near ITPL",               "Bengaluru",    "Karnataka",   "560066", 12.978900, 77.730560, False),
    ("9000000004", "Home", "A-12, Srinivasa Nagar, Jubilee Hills",       None,        "Near Jubilee Hills Checkpost", "Hyderabad","Telangana", "500001", 17.432730, 78.407040, True),
    ("9000000004", "Work", "Cyber Towers, Phase 2, Hitech City",         None,        "Near Hitech City Metro",  "Hyderabad",    "Telangana",   "500081", 17.444920, 78.381210, False),
    ("9000000005", "Home", "22, Gandhi Nagar, T. Nagar",                 None,        "Near Pondy Bazaar",       "Chennai",      "Tamil Nadu",  "600001", 13.040140, 80.234550, True),
    ("9000000005", "Work", "OMR IT Corridor, Sholinganallur",            None,        "Near Sholinganallur Signal","Chennai",    "Tamil Nadu",  "600119", 12.900540, 80.227730, False),
    ("9000000006", "Home", "B-45, Model Town, Phase 2",                  None,        "Near Model Town Metro",   "New Delhi",    "Delhi",       "110009", 28.704060, 77.194300, True),
    ("9000000006", "Work", "Block A, Nehru Place",                       None,        "Near Nehru Place Metro",  "New Delhi",    "Delhi",       "110019", 28.548820, 77.251900, False),
    ("9000000007", "Home", "C-7, Naranpura Society, Naranpura",          None,        "Near Naranpura Cross Roads","Ahmedabad",  "Gujarat",     "380013", 23.059480, 72.561670, True),
    ("9000000007", "Work", "Plot 12, GIFT City, Sector 1",               None,        "Near GIFT City Gate",     "Gandhinagar",  "Gujarat",     "382355", 23.166710, 72.685110, False),
    ("9000000008", "Home", "12, Civil Lines, Ajmer Road",                None,        "Near Jaipur Junction",    "Jaipur",       "Rajasthan",   "302001", 26.921560, 75.768400, True),
    ("9000000008", "Work", "Sitapura Industrial Area, Tonk Road",        None,        "Near Sitapura RIICO",     "Jaipur",       "Rajasthan",   "302022", 26.768450, 75.846750, False),
    ("9000000009", "Home", "Flat 204, BF Block, Salt Lake City",         None,        "Near Salt Lake Stadium",  "Kolkata",      "West Bengal", "700064", 22.572645, 88.363890, True),
    ("9000000009", "Work", "Sector V, Saltlake Electronics Complex",     None,        "Near TCS Gate 3",         "Kolkata",      "West Bengal", "700091", 22.578480, 88.432860, False),
    ("9000000010", "Home", "House 34, Sector 17-D",                      None,        "Near Sector 17 Bus Stand","Chandigarh",   "Chandigarh",  "160017", 30.741480, 76.778660, True),
    ("9000000010", "Work", "IT Park, Phase 8-B, Mohali",                 None,        "Near IT Park Chowk",      "Chandigarh",   "Chandigarh",  "160059", 30.706440, 76.712100, False),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        for row in ADDRESS_DATA:
            phone, label, line1, line2, lm, city, state, pin_code, lat, lng, is_default = row

            user = db.query(User).filter(User.phone == phone).first()
            if not user:
                print(f"  ! User {phone} not found — run users_seeder.py first")
                continue

            exists = (
                db.query(UserAddress)
                .filter(
                    UserAddress.user_reference_id == user.user_id,
                    UserAddress.label == label,
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            db.add(UserAddress(
                user_reference_id=user.user_id,
                label=label,
                address_line1=line1,
                address_line2=line2,
                landmark=lm,
                city=city,
                state=state,
                pin_code=pin_code,
                country="IN",
                latitude=lat,
                longitude=lng,
                is_default=is_default,
                is_active=True,
            ))
            inserted += 1
            print(f"  + {phone} — {label} ({city})")

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
