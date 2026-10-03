"""
Payments are internal in this phase: the only payment rows are wallet
top-ups (method 'internal_wallet', no gateway). A "refund" therefore cannot
send money anywhere; what an admin can do is reverse a top-up that should not
have happened, which takes the amount back out of the wallet.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import record_audit, business_event
from app.core.clock import now_utc
from app.core.errors import DomainError
from app.domain import ledger, notify
from app.domain.pricing import money, ZERO
from app.repositories.payment_repository import PaymentRepository


class AdminPaymentService:

    @staticmethod
    def list_payments(db: Session, status: str = None, method: str = None, page: int = 1, limit: int = 20):
        items, total = PaymentRepository.get_all(db, status=status, method=method, page=page, limit=limit)
        return {"success": True, "total": total, "payments": items}

    @staticmethod
    def get_payment(db: Session, payment_id):
        payment = PaymentRepository.get_by_id(db, payment_id)
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        return payment

    @staticmethod
    def reverse_topup(db: Session, payment_id, payload, admin_id: str, ip: str | None = None):
        payment = PaymentRepository.get_by_id(db, payment_id)
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        if payment.purpose != "wallet_topup" or payment.gateway is not None:
            raise DomainError("Only internal wallet top-ups can be reversed in this phase")
        if payment.status not in ("completed", "partially_refunded"):
            raise DomainError(f"This payment is '{payment.status}' and cannot be reversed")

        already = money(payment.refund_amount)
        remaining = money(payment.amount) - already
        amount = money(payload.amount) if payload.amount is not None else remaining
        if amount <= ZERO or amount > remaining:
            raise DomainError(f"At most Rs {remaining} of this top-up can still be reversed")

        before = {"status": payment.status, "refund_amount": payment.refund_amount}
        # The wallet must still hold the money; the debit never goes below 0
        txn = ledger.post_customer(
            db, payment.user_reference_id,
            type="debit", amount=amount, reason="refund",
            idempotency_key=f"topup_reversal:{payment.payment_id}:{already}",
            reference_type="payment", reference_id=payment.payment_id,
            description=payload.reason,
            created_by=admin_id,
        )

        payment.refund_amount = already + amount
        payment.status = "refunded" if payment.refund_amount >= money(payment.amount) else "partially_refunded"
        payment.refunded_at = now_utc()
        record_audit(
            db, table="subscription.payments", record_id=payment.payment_id,
            old=before, new={"status": payment.status, "refund_amount": payment.refund_amount, "reason": payload.reason},
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        notify.customer(
            db, payment.user_reference_id, "payment_refund", "Wallet top-up reversed",
            f"Rs {amount} from a wallet top-up was reversed by Orleeno support. {payload.reason}",
            {"payment_id": str(payment.payment_id)},
        )
        db.commit()
        business_event("payment.topup_reversed", payment_id=payment.payment_id, amount=amount, admin_id=admin_id)
        return {
            "success": True,
            "message": f"Rs {amount} reversed from the customer's wallet",
            "refund_amount": amount,
            "balance_after": txn.balance_after,
            "payment_status": payment.status,
        }
