from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user_model import User
from app.models.user_address_model import UserAddress
from app.models.subscription_model import Subscription
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction
from app.repositories.wallet_repository import WalletRepository

VALID_STATUSES = {"active", "inactive", "suspended"}


class AdminUserService:

    @staticmethod
    def list_users(db: Session, status: str = None, search: str = None, page: int = 1, limit: int = 20):
        query = db.query(User)
        if status:
            query = query.filter(User.status == status)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                User.full_name.ilike(pattern) |
                User.phone.ilike(pattern) |
                User.email.ilike(pattern)
            )
        total = query.count()
        users = query.order_by(User.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page, "users": users}

    @staticmethod
    def get_user_detail(db: Session, user_id: str):
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        addresses = db.query(UserAddress).filter(UserAddress.user_reference_id == user_id).all()
        subscriptions = (
            db.query(Subscription)
            .filter(Subscription.user_reference_id == user_id)
            .order_by(Subscription.created_at.desc())
            .all()
        )
        wallet = db.query(Wallet).filter(Wallet.user_reference_id == user_id).first()
        txns = (
            db.query(WalletTransaction)
            .filter(WalletTransaction.user_reference_id == user_id)
            .order_by(WalletTransaction.created_at.desc())
            .limit(20)
            .all()
        )

        return {
            "success": True,
            "user": user,
            "addresses": addresses,
            "subscriptions": subscriptions,
            "wallet": wallet,
            "recent_transactions": txns
        }

    @staticmethod
    def update_user_status(db: Session, user_id: str, payload, admin_id: str):
        if payload.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}")

        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if payload.status == "inactive":
            active_subs = db.query(Subscription).filter(
                Subscription.user_reference_id == user_id,
                Subscription.status == "active"
            ).count()
            if active_subs:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot deactivate user with {active_subs} active subscription(s). Cancel them first."
                )

        user.status = payload.status
        db.commit()

        return {"success": True, "message": f"User status updated to '{payload.status}'", "user_id": user_id}

    @staticmethod
    def adjust_wallet(db: Session, user_id: str, payload, admin_id: str):
        if payload.type not in ("credit", "debit"):
            raise HTTPException(status_code=400, detail="type must be 'credit' or 'debit'")

        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        amount = Decimal(str(payload.amount))
        wallet = WalletRepository.get_or_create(db, user_id)
        balance_before = Decimal(str(wallet.balance))

        if payload.type == "debit" and amount > balance_before:
            raise HTTPException(status_code=400, detail=f"Insufficient balance. Available: ₹{balance_before}")

        if payload.type == "credit":
            WalletRepository.credit_balance(db, wallet, amount)
        else:
            WalletRepository.deduct_balance(db, wallet, amount)

        WalletRepository.create_transaction(db, {
            "wallet_reference_id": wallet.wallet_id,
            "user_reference_id": user_id,
            "type": payload.type,
            "reason": "adjustment",
            "amount": amount,
            "balance_before": balance_before,
            "balance_after": Decimal(str(wallet.balance)),
            "description": payload.reason,
            "created_by": admin_id,
        })
        db.commit()

        return {
            "success": True,
            "message": f"Wallet {payload.type}ed ₹{amount}",
            "balance_before": balance_before,
            "balance_after": Decimal(str(wallet.balance))
        }

    @staticmethod
    def cancel_subscription(db: Session, subscription_id: str, reason: str, admin_id: str):
        sub = db.query(Subscription).filter(Subscription.subscription_id == subscription_id).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        if sub.status == "cancelled":
            raise HTTPException(status_code=400, detail="Subscription is already cancelled")

        from datetime import datetime, timezone
        sub.status = "cancelled"
        sub.cancelled_at = datetime.now(timezone.utc)
        sub.cancel_reason = reason or "Cancelled by admin"
        db.commit()

        return {"success": True, "message": "Subscription cancelled", "subscription_id": subscription_id}
