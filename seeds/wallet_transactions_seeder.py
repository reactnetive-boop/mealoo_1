"""
Seeds wallet transactions (credits/debits) for each user wallet.
Requires: users, wallets seeders.
"""
import sys
import os
from decimal import Decimal

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user_model import User
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction

# (phone, type, reason, amount, description)
TRANSACTIONS = [
    ("9000000001", "credit", "topup",          2500.00, "Wallet top-up via UPI"),
    ("9000000001", "debit",  "order_placed",    150.00, "Lunch — Dal Makhani Thali"),
    ("9000000001", "debit",  "order_placed",    100.00, "Breakfast — Punjabi Breakfast Box"),
    ("9000000002", "credit", "topup",          2000.00, "Wallet top-up via Net Banking"),
    ("9000000002", "debit",  "order_placed",     90.00, "Breakfast — South Indian Breakfast Plate"),
    ("9000000003", "credit", "topup",          2500.00, "Wallet top-up via Debit Card"),
    ("9000000003", "debit",  "order_placed",    260.00, "Lunch — Hyderabadi Chicken Dum Biryani"),
    ("9000000003", "debit",  "order_placed",    260.00, "Lunch — Hyderabadi Chicken Dum Biryani (extra)"),
    ("9000000004", "credit", "topup",          2000.00, "Wallet top-up via UPI"),
    ("9000000004", "debit",  "order_placed",    140.00, "Lunch — Gujarati Tiffin Box"),
    ("9000000005", "credit", "topup",          1500.00, "Wallet top-up via Credit Card"),
    ("9000000005", "debit",  "order_placed",    180.00, "Lunch — Kerala Sadya Combo (extra)"),
    ("9000000005", "credit", "refund",          130.00, "Refund — subscription cancellation"),
    ("9000000006", "credit", "topup",          1500.00, "Wallet top-up via UPI"),
    ("9000000007", "credit", "topup",          1500.00, "Wallet top-up via Net Banking"),
    ("9000000007", "debit",  "order_placed",    370.00, "Dinner — Mutton Biryani Box (extra)"),
    ("9000000007", "credit", "refund",          370.00, "Refund — order cancelled"),
    ("9000000008", "credit", "topup",          1500.00, "Wallet top-up via UPI"),
    ("9000000009", "credit", "topup",           500.00, "Wallet top-up via UPI"),
    ("9000000010", "credit", "topup",           500.00, "Wallet top-up via UPI"),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        # Group by phone to compute running balance
        from collections import defaultdict
        by_phone = defaultdict(list)
        for row in TRANSACTIONS:
            by_phone[row[0]].append(row)

        for phone, txns in by_phone.items():
            user = db.query(User).filter(User.phone == phone).first()
            if not user:
                continue
            wallet = db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).first()
            if not wallet:
                continue

            # Check how many transactions already exist for this wallet
            existing_count = (
                db.query(WalletTransaction)
                .filter(WalletTransaction.wallet_reference_id == wallet.wallet_id)
                .count()
            )
            if existing_count >= len(txns):
                skipped += len(txns)
                continue

            # Rebuild balance from scratch using transactions to seed
            running_balance = Decimal("0.00")
            for _, txn_type, reason, amount, description in txns:
                amount_d = Decimal(str(amount))
                balance_before = running_balance
                if txn_type == "credit":
                    running_balance += amount_d
                else:
                    running_balance -= amount_d
                balance_after = running_balance

                db.add(WalletTransaction(
                    wallet_reference_id=wallet.wallet_id,
                    user_reference_id=user.user_id,
                    type=txn_type,
                    reason=reason,
                    amount=amount_d,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    description=description,
                    created_by=user.user_id,
                ))
                inserted += 1

            print(f"  + {user.full_name} ({phone}) — {len(txns)} transactions")

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
