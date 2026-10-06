from sqlalchemy.orm import Session

from app.models.complaint_model import Complaint


class ComplaintRepository:

    @staticmethod
    def create(
        db: Session,
        complaint_data: dict
    ):

        complaint = Complaint(**complaint_data)

        db.add(complaint)

        db.flush()

        db.refresh(complaint)

        return complaint

    @staticmethod
    def get_by_id(
        db: Session,
        complaint_id
    ):

        return (
            db.query(Complaint)
            .filter(
                Complaint.complaint_id == complaint_id
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
            db.query(Complaint)
            .filter(
                Complaint.user_reference_id == user_id
            )
            .order_by(
                Complaint.created_at.desc()
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def count_by_user(db: Session, user_id) -> int:
        return (
            db.query(Complaint)
            .filter(
                Complaint.user_reference_id == user_id
            )
            .count()
        )

    @staticmethod
    def update(
        db: Session,
        complaint: Complaint,
        update_data: dict
    ):

        for key, value in update_data.items():

            setattr(complaint, key, value)

        db.flush()

        db.refresh(complaint)

        return complaint

    @staticmethod
    def withdraw(
        db: Session,
        complaint: Complaint
    ):

        complaint.status = "closed"

        db.flush()

        db.refresh(complaint)

        return complaint
