"""
Customer wallet.

Current phase: no payment gateway. Customers top up through the internal
wallet top-up below, which is recorded as a Payment row (method
'internal_wallet', no gateway, no transaction id) plus a ledger credit.
Nothing pretends a UPI / card transaction happened.

Future gateway: initiate a 'pending' Payment, and only on a *verified*
gateway webhook call `credit_payment()` with that payment. It applies the
same ledger credit, so balances, history and admin refunds work unchanged.
"""


from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import business_event, security_event
from app.core.clock import now_utc, now_local
from app.core.config import WALLET_TOPUP_MAX_AMOUNT, WALLET_TOPUP_DAILY_LIMIT, WALLET_SELF_TOPUP_ENABLED
from app.core.errors import DomainError
from app.domain import ledger
from app.domain.pricing import ZERO, money
from app.models.payment_model import Payment
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction
from app.repositories.wallet_repository import WalletRepository


def credit_payment(db: Session, payment: Payment, description: str) -> WalletTransaction:
    """Credit a completed payment to the wallet exactly once."""
    return ledger.post_customer(
        db,
        payment.user_reference_id,
        type="credit",
        amount=payment.amount,
        reason="topup",
        idempotency_key=f"topup:{payment.payment_id}",
        reference_type="payment",
        reference_id=payment.payment_id,
        description=description,
        created_by=payment.user_reference_id,
    )


class WalletService:

    @staticmethod
    def get_wallet_details(db: Session, user_id: str):
        # Read only: the wallet row is created on the first credit, not by viewing it
        wallet = db.query(Wallet).filter(Wallet.user_reference_id == user_id).first() or {
            "wallet_id": None,
            "user_reference_id": user_id,
            "balance": money(ZERO),
            "created_at": None,
            "updated_at": None,
        }
        transactions = WalletRepository.get_transactions_by_user(db, user_id)
        return {"success": True, "wallet": wallet, "transactions": transactions}

    @staticmethod
    def get_transaction_history(db: Session, user_id: str):
        transactions = WalletRepository.get_transactions_by_user(db, user_id, limit=200)
        return {"success": True, "total": len(transactions), "transactions": transactions}

    @staticmethod
    def recharge(db: Session, user_id: str, payload, idempotency_key: str | None = None):

        if not WALLET_SELF_TOPUP_ENABLED:
            raise DomainError("Wallet top-up is not available right now", 403)

        amount = money(payload.amount)
        if amount > money(WALLET_TOPUP_MAX_AMOUNT):
            raise DomainError(f"A single top-up can be at most Rs {money(WALLET_TOPUP_MAX_AMOUNT)}")

        key = f"topup_request:{user_id}:{idempotency_key}" if idempotency_key else None
        if key:
            existing = db.query(Payment).filter(Payment.idempotency_key == key).first()
            if existing:
                txn = ledger.customer_txn_exists(db, f"topup:{existing.payment_id}")
                return {
                    "success": True,
                    "message": "Wallet already recharged",
                    "balance_before": txn.balance_before,
                    "amount_added": txn.amount,
                    "balance_after": txn.balance_after,
                    "payment_id": existing.payment_id,
                }

        wallet = ledger.lock_customer_wallet(db, user_id)

        day_start = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
        topped_today = (
            db.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(
                Payment.user_reference_id == user_id,
                Payment.purpose == "wallet_topup",
                Payment.status == "completed",
                Payment.paid_at >= day_start,
            )
            .scalar()
        )
        if money(topped_today) + amount > money(WALLET_TOPUP_DAILY_LIMIT):
            security_event("wallet.topup_daily_limit", user_id=user_id, attempted=amount)
            raise DomainError(f"Daily top-up limit of Rs {money(WALLET_TOPUP_DAILY_LIMIT)} reached")

        payment = Payment(
            user_reference_id=user_id,
            purpose="wallet_topup",
            amount=amount,
            currency="INR",
            method="internal_wallet",
            status="completed",
            gateway=None,
            paid_at=now_utc(),
            idempotency_key=key,
        )
        db.add(payment)
        db.flush()

        balance_before = money(wallet.balance)
        txn = credit_payment(db, payment, payload.description or "Wallet top-up")
        db.commit()
        business_event("wallet.topup", user_id=user_id, amount=amount, payment_id=payment.payment_id)

        return {
            "success": True,
            "message": "Wallet recharged successfully",
            "balance_before": balance_before,
            "amount_added": amount,
            "balance_after": txn.balance_after,
            "payment_id": payment.payment_id,
        }
