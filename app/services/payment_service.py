import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.payment_repository import PaymentRepository
from app.repositories.wallet_repository import WalletRepository
from app.services.notification_service import NotificationService


class PaymentService:

    @staticmethod
    def initiate_topup(db: Session, user_id: str, amount: Decimal):
        payment = PaymentRepository.create(db, {
            "user_reference_id": user_id,
            "amount": amount,
            "method": "upi",
            "status": "pending",
            "purpose": "wallet_topup",
            "gateway": "mock",
            "gateway_order_id": uuid.uuid4().hex
        })
        db.commit()
        db.refresh(payment)

        return {
            "success": True,
            "message": "Payment initiated",
            "payment_id": payment.payment_id,
            "gateway_order_id": payment.gateway_order_id,
            "amount": payment.amount
        }

    @staticmethod
    def confirm_topup(db: Session, user_id: str, payment_id, gateway_txn_id: str):
        payment = PaymentRepository.get_by_id_and_user(db, payment_id, user_id)
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        if payment.status != "pending":
            raise HTTPException(status_code=400, detail=f"Payment is already '{payment.status}'")

        try:
            wallet = WalletRepository.get_or_create(db, user_id)
            balance_before = Decimal(str(wallet.balance))

            WalletRepository.credit_balance(db, wallet, payment.amount)
            balance_after = Decimal(str(wallet.balance))

            WalletRepository.create_transaction(db, {
                "wallet_reference_id": wallet.wallet_id,
                "user_reference_id": user_id,
                "type": "credit",
                "reason": "topup",
                "amount": payment.amount,
                "balance_before": balance_before,
                "balance_after": balance_after,
                "description": f"Wallet top-up via payment {payment.payment_id}",
                "created_by": user_id,
                "reference_id": payment.payment_id,
                "reference_type": "payment"
            })

            payment.status = "completed"
            payment.gateway_txn_id = gateway_txn_id

            db.commit()
            db.refresh(payment)

            NotificationService.create_notification(
                db,
                user_id,
                type="wallet_topup",
                title="Wallet recharged",
                body=f"₹{payment.amount} was added to your wallet.",
                data={"payment_id": str(payment.payment_id)}
            )

            return {
                "success": True,
                "message": "Payment confirmed and wallet credited",
                "balance_before": balance_before,
                "amount_added": payment.amount,
                "balance_after": balance_after
            }

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Payment confirmation failed: {str(e)}")

    @staticmethod
    def list_my_payments(db: Session, user_id: str):
        payments = PaymentRepository.get_all_by_user(db, user_id)
        return {
            "success": True,
            "total": len(payments),
            "payments": payments
        }

    @staticmethod
    def get_payment(db: Session, user_id: str, payment_id):
        payment = PaymentRepository.get_by_id_and_user(db, payment_id, user_id)
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        return payment
