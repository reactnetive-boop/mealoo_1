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
                Payment.user_reference_id == user_id
            )
            .order_by(
                Payment.created_at.desc()
            )
            .all()
        )

    @staticmethod
    def get_by_id(db: Session, payment_id):
        return (
            db.query(Payment)
            .filter(Payment.payment_id == payment_id)
            .first()
        )

    @staticmethod
    def get_by_id_and_user(db: Session, payment_id, user_id):
        return (
            db.query(Payment)
            .filter(
                Payment.payment_id == payment_id,
                Payment.user_reference_id == user_id
            )
            .first()
        )

    @staticmethod
    def get_all(db: Session, status: str = None, method: str = None, page: int = 1, limit: int = 20):
        query = db.query(Payment)
        if status:
            query = query.filter(Payment.status == status)
        if method:
            query = query.filter(Payment.method == method)

        total = query.count()
        offset = (page - 1) * limit
        items = (
            query.order_by(Payment.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total
