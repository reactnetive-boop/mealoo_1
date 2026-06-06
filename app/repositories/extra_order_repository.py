from sqlalchemy.orm import Session

from app.models.extra_order_model import ExtraOrder


class ExtraOrderRepository:

    @staticmethod
    def create_order(
        db: Session,
        order_data: dict
    ):

        order = ExtraOrder(**order_data)

        db.add(order)

        db.flush()

        return order

    @staticmethod
    def get_by_id(
        db: Session,
        order_id
    ):

        return (
            db.query(ExtraOrder)
            .filter(
                ExtraOrder.id == order_id
            )
            .first()
        )

    @staticmethod
    def get_all_by_user(
        db: Session,
        user_id
    ):

        return (
            db.query(ExtraOrder)
            .filter(
                ExtraOrder.user_id == user_id
            )
            .order_by(
                ExtraOrder.created_at.desc()
            )
            .all()
        )
