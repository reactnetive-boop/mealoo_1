from sqlalchemy.orm import Session

from app.models.provider_complaint_model import ProviderComplaint


class ProviderComplaintRepository:

    @staticmethod
    def create(db: Session, data: dict) -> ProviderComplaint:
        complaint = ProviderComplaint(**data)
        db.add(complaint)
        db.commit()
        db.refresh(complaint)
        return complaint

    @staticmethod
    def get_by_id(db: Session, complaint_id) -> ProviderComplaint:
        return (
            db.query(ProviderComplaint)
            .filter(ProviderComplaint.provider_complaint_id == complaint_id)
            .first()
        )

    @staticmethod
    def get_by_id_and_provider(db: Session, complaint_id, provider_id) -> ProviderComplaint:
        return (
            db.query(ProviderComplaint)
            .filter(
                ProviderComplaint.provider_complaint_id == complaint_id,
                ProviderComplaint.provider_reference_id == provider_id
            )
            .first()
        )

    @staticmethod
    def get_all_by_provider(db: Session, provider_id, against: str = None, status: str = None):
        query = (
            db.query(ProviderComplaint)
            .filter(ProviderComplaint.provider_reference_id == provider_id)
        )
        if against:
            query = query.filter(ProviderComplaint.against == against)
        if status:
            query = query.filter(ProviderComplaint.status == status)
        return query.order_by(ProviderComplaint.created_at.desc()).all()

    @staticmethod
    def update(db: Session, complaint: ProviderComplaint, data: dict) -> ProviderComplaint:
        for key, value in data.items():
            setattr(complaint, key, value)
        db.commit()
        db.refresh(complaint)
        return complaint

    @staticmethod
    def withdraw(db: Session, complaint: ProviderComplaint) -> ProviderComplaint:
        complaint.status = "closed"
        db.commit()
        db.refresh(complaint)
        return complaint
