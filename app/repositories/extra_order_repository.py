from datetime import date as date_type

from sqlalchemy.orm import Session

from app.models.extra_order_model import ExtraOrder


class ExtraOrderRepository:

    @staticmethod
    def get_by_id(
        db: Session,
        order_id
    ):

        return (
            db.query(ExtraOrder)
            .filter(
                ExtraOrder.extra_order_id == order_id
            )
            .first()
        )

    @staticmethod
    def get_all_by_user(
        db: Session,
        user_id,
        offset: int = 0,
        limit: int | None = None,
    ):

        return (
            db.query(ExtraOrder)
            .filter(
                ExtraOrder.user_reference_id == user_id
            )
            .order_by(
                ExtraOrder.created_at.desc()
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def count_by_user(db: Session, user_id) -> int:
        return (
            db.query(ExtraOrder)
            .filter(
                ExtraOrder.user_reference_id == user_id
            )
            .count()
        )

    @staticmethod
    def get_all_by_vendor(
        db: Session,
        vendor_id,
        delivery_date: date_type = None,
        status: str = None
    ):
        query = (
            db.query(ExtraOrder)
            .filter(ExtraOrder.vendor_reference_id == vendor_id)
        )
        if delivery_date:
            query = query.filter(ExtraOrder.delivery_date == delivery_date)
        if status:
            query = query.filter(ExtraOrder.status == status)
        return query.order_by(ExtraOrder.delivery_date.asc(), ExtraOrder.created_at.desc()).all()

    @staticmethod
    def get_by_id_and_vendor(
        db: Session,
        order_id,
        vendor_id
    ):
        return (
            db.query(ExtraOrder)
            .filter(
                ExtraOrder.extra_order_id == order_id,
                ExtraOrder.vendor_reference_id == vendor_id
            )
            .first()
        )
