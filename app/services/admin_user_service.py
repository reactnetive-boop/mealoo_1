from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import record_audit, business_event
from app.core.errors import DomainError
from app.domain import ledger
from app.domain.pricing import money
from app.models.user_model import User
from app.models.user_address_model import UserAddress
from app.models.subscription_model import Subscription
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction
from app.services.admin_views import user_view, address_view, subscription_admin_view
from app.services.auth_common import revoke_sessions
from app.services.subscription_service import SubscriptionService

VALID_STATUSES = ("active", "inactive", "suspended")


def _user(db: Session, user_id, lock: bool = False) -> User:
    q = db.query(User).filter(User.user_id == user_id)
    if lock:
        q = q.with_for_update()
    user = q.first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _txn_view(t) -> dict:
    return {
        "wallet_transaction_id": t.wallet_transaction_id,
        "type": t.type,
        "reason": t.reason,
        "amount": t.amount,
        "balance_before": t.balance_before,
        "balance_after": t.balance_after,
        "reference_type": t.reference_type,
        "reference_id": t.reference_id,
        "description": t.description,
        "created_at": t.created_at,
    }


class AdminUserService:

    @staticmethod
    def list_users(db: Session, status: str = None, search: str = None, page: int = 1, limit: int = 20):
        query = db.query(User)
        if status:
            if status not in VALID_STATUSES:
                raise DomainError(f"status must be one of: {', '.join(VALID_STATUSES)}")
            query = query.filter(User.status == status)
        if search:
            pattern = f"%{search}%"
            query = query.filter(User.full_name.ilike(pattern) | User.phone.ilike(pattern) | User.email.ilike(pattern))
        total = query.count()
        users = query.order_by(User.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page, "users": [user_view(u) for u in users]}

    @staticmethod
    def get_user_detail(db: Session, user_id: str):
        user = _user(db, user_id)
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
            "user": user_view(user),
            "addresses": [address_view(a) for a in addresses],
            "subscriptions": [subscription_admin_view(s) for s in subscriptions],
            "wallet": {
                "wallet_id": wallet.wallet_id,
                "user_reference_id": wallet.user_reference_id,
                "balance": wallet.balance,
                "created_at": wallet.created_at,
                "updated_at": wallet.updated_at,
            } if wallet else None,
            "recent_transactions": [_txn_view(t) for t in txns],
        }

    @staticmethod
    def update_user_status(db: Session, user_id: str, payload, admin_id: str, ip: str | None = None):
        if payload.status not in VALID_STATUSES:
            raise DomainError(f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}")

        user = _user(db, user_id, lock=True)
        before = user_view(user)

        if payload.status != "active":
            open_subs = db.query(Subscription).filter(
                Subscription.user_reference_id == user_id,
                Subscription.status.in_(("active", "paused")),
            ).count()
            if open_subs:
                raise DomainError(
                    f"Cannot block a customer with {open_subs} running subscription(s). Cancel them first "
                    "(refunds go to the customer's wallet)."
                )
            # blocked accounts lose every session immediately
            revoke_sessions(user)

        user.status = payload.status
        record_audit(
            db, table="auth.users", record_id=user.user_id,
            old=before, new={**user_view(user), "reason": payload.reason},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return {"success": True, "message": f"User status updated to '{payload.status}'", "user_id": user_id}

    @staticmethod
    def adjust_wallet(db: Session, user_id: str, payload, admin_id: str, idempotency_key: str, ip: str | None = None):
        if payload.type not in ("credit", "debit"):
            raise DomainError("type must be 'credit' or 'debit'")
        _user(db, user_id)

        amount = money(payload.amount)
        txn = ledger.post_customer(
            db, user_id,
            type=payload.type, amount=amount, reason="adjustment",
            idempotency_key=f"admin_adjust:user:{idempotency_key}",
            reference_type="admin_adjustment",
            description=payload.reason if not payload.description else f"{payload.reason} - {payload.description}",
            created_by=admin_id,
        )
        ledger.post_platform(
            db, entry_type="manual_adjustment",
            direction="debit" if payload.type == "credit" else "credit",
            amount=amount, reference_type="wallet_transaction", reference_id=txn.wallet_transaction_id,
            idempotency_key=f"platform:admin_adjust:user:{idempotency_key}",
            description=payload.reason,
        )
        record_audit(
            db, table="subscription.wallet_transactions", record_id=txn.wallet_transaction_id, operation="I",
            new={"user_id": user_id, "type": payload.type, "amount": amount, "reason": payload.reason},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        business_event("wallet.admin_adjust", owner="user", owner_id=user_id, type=payload.type, amount=amount, admin_id=admin_id)
        return {
            "success": True,
            "message": f"Wallet {payload.type}ed Rs {amount}",
            "balance_before": txn.balance_before,
            "balance_after": txn.balance_after,
        }

    @staticmethod
    def cancel_subscription(db: Session, subscription_id: str, reason: str, admin_id: str, ip: str | None = None):
        sub = (
            db.query(Subscription)
            .filter(Subscription.subscription_id == subscription_id)
            .with_for_update()
            .first()
        )
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        before = subscription_admin_view(sub)
        result = SubscriptionService.cancel(db, sub, reason=reason or "Cancelled by Orleeno support", actor="admin")
        record_audit(
            db, table="subscription.subscriptions", record_id=sub.subscription_id,
            old=before, new={**subscription_admin_view(sub), **result},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return {
            "success": True,
            "message": f"Subscription cancelled. Rs {result['refund_amount']} refunded to the customer's wallet.",
            "subscription_id": subscription_id,
            **result,
        }
