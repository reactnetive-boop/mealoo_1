from sqlalchemy.orm import Session

from app.models.payment_model import Payment


class PaymentRepository:

    @staticmethod
    def create(
        db: Session,
        payment_data: dict
    ):

        payment = Payment(**payment_data)

        db.add(payment)

        db.flush()

        return payment

    @staticmethod
    def get_all_by_user(
        db: Session,
        user_id
    ):

        return (
            db.query(Payment)
            .filter(
                Payment.user_id == user_id
            )
            .order_by(
                Payment.created_at.desc()
            )
            .all()
        )
