from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.payment_repository import PaymentRepository


class PaymentService:
    """
    Read access to the customer's payment records.

    There is deliberately no initiate / confirm flow here: no payment gateway
    is integrated in this phase and the old mock confirm endpoint (which
    credited wallets on a made-up transaction id) has been removed. See
    wallet_service.credit_payment for the hook a verified gateway webhook
    will use.
    """

    @staticmethod
    def list_my_payments(db: Session, user_id: str):
        payments = PaymentRepository.get_all_by_user(db, user_id)
        return {"success": True, "total": len(payments), "payments": payments}

    @staticmethod
    def get_payment(db: Session, user_id: str, payment_id):
        payment = PaymentRepository.get_by_id_and_user(db, payment_id, user_id)
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        return payment
