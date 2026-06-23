"""
Seeds notifications for users.
Requires: users seeder.
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user_model import User
from app.models.notification_model import Notification

# (phone, type, title, body, is_read)
NOTIFICATIONS = [
    ("9000000001", "order_update",    "Order Out for Delivery",       "Your lunch order from Sharma Ji's Kitchen is on the way! OTP: 4821", False),
    ("9000000001", "wallet",          "Wallet Topped Up",              "₹2,500 has been added to your Mealoo wallet. New balance: ₹2,500.", True),
    ("9000000002", "order_update",    "Order Delivered",               "Your breakfast from Kerala Kitchen has been delivered. Enjoy your meal!", True),
    ("9000000002", "promo",           "Weekend Special Offer",         "Get 15% off on all South Indian meals this weekend! Use code WEEKEND15.", False),
    ("9000000003", "subscription",    "Subscription Activated",        "Your weekly lunch subscription with Spice Route Biryani is now active.", True),
    ("9000000003", "order_update",    "Order Delivered",               "Your Hyderabadi Chicken Dum Biryani has been delivered. Rate your experience!", True),
    ("9000000004", "subscription",    "Subscription Reminder",         "Your monthly subscription with Patel Tiffin Service renews in 3 days.", False),
    ("9000000005", "subscription",    "Subscription Expired",          "Your weekly dinner subscription has expired. Renew to continue enjoying meals.", True),
    ("9000000006", "subscription",    "Subscription Paused",           "Your dinner subscription with Kerala Kitchen is now paused. Resume anytime.", True),
    ("9000000007", "order_update",    "Order Cancelled",               "Your extra order for Mutton Biryani Box has been cancelled. Refund initiated.", True),
    ("9000000008", "wallet",          "Wallet Topped Up",              "₹1,500 has been added to your Mealoo wallet. New balance: ₹1,500.", True),
    ("9000000009", "promo",           "Try Our New Kolkata Special",   "Taste authentic Bengali cuisine with our new partner restaurants in Kolkata!", False),
    ("9000000010", "promo",           "First Subscription Offer",      "Subscribe for your first meal plan and get 20% off. Limited time offer!", False),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        for phone, notif_type, title, body, is_read in NOTIFICATIONS:
            user = db.query(User).filter(User.phone == phone).first()
            if not user:
                continue

            exists = (
                db.query(Notification)
                .filter(
                    Notification.user_reference_id == user.user_id,
                    Notification.title == title,
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            db.add(Notification(
                user_reference_id=user.user_id,
                type=notif_type,
                title=title,
                body=body,
                is_read=is_read,
            ))
            inserted += 1
            print(f"  + {user.full_name} — {title}")

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
