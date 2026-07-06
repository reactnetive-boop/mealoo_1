from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.payment_repository import PaymentRepository
from app.repositories.wallet_repository import WalletRepository
from app.services.notification_service import NotificationService


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
    def refund_payment(db: Session, payment_id, payload):
        payment = PaymentRepository.get_by_id(db, payment_id)
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        if payment.status != "completed":
            raise HTTPException(status_code=400, detail=f"Only 'completed' payments can be refunded (current status: '{payment.status}')")

        refund_amount = payload.refund_amount or payment.amount
        if refund_amount > payment.amount:
            raise HTTPException(status_code=400, detail="Refund amount cannot exceed the original payment amount")

        try:
            wallet = WalletRepository.get_by_user_id(db, payment.user_reference_id)
            if not wallet:
                raise HTTPException(status_code=404, detail="User wallet not found")

            debit_amount = min(refund_amount, wallet.balance)
            balance_before = Decimal(str(wallet.balance))

            WalletRepository.deduct_balance(db, wallet, debit_amount)
            balance_after = Decimal(str(wallet.balance))

            WalletRepository.create_transaction(db, {
                "wallet_reference_id": wallet.wallet_id,
                "user_reference_id": payment.user_reference_id,
                "type": "debit",
                "reason": "refund",
                "amount": debit_amount,
                "balance_before": balance_before,
                "balance_after": balance_after,
                "description": payload.reason or f"Refund for payment {payment.payment_id}",
                "reference_id": payment.payment_id,
                "reference_type": "payment"
            })

            payment.status = "refunded"
            payment.refund_amount = refund_amount
            payment.refunded_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(payment)

            NotificationService.create_notification(
                db,
                payment.user_reference_id,
                type="payment_refund",
                title="Payment refunded",
                body=f"₹{refund_amount} was refunded and deducted from your wallet balance.",
                data={"payment_id": str(payment.payment_id)}
            )

            return {"success": True, "message": "Payment refunded successfully", "refund_amount": refund_amount}

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Refund failed: {str(e)}")
