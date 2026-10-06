from sqlalchemy.orm import Session

from app.models.delivery_boy_complaint_model import DeliveryBoyComplaint


class DeliveryBoyComplaintRepository:

    @staticmethod
    def create(db: Session, data: dict) -> DeliveryBoyComplaint:
        complaint = DeliveryBoyComplaint(**data)
        db.add(complaint)
        db.flush()
        db.refresh(complaint)
        return complaint

    @staticmethod
    def get_by_id(db: Session, complaint_id) -> DeliveryBoyComplaint:
        return (
            db.query(DeliveryBoyComplaint)
            .filter(DeliveryBoyComplaint.delivery_boy_complaint_id == complaint_id)
            .first()
        )

    @staticmethod
    def get_by_id_and_delivery_boy(db: Session, complaint_id, delivery_boy_id) -> DeliveryBoyComplaint:
        return (
            db.query(DeliveryBoyComplaint)
            .filter(
                DeliveryBoyComplaint.delivery_boy_complaint_id == complaint_id,
                DeliveryBoyComplaint.delivery_boy_reference_id == delivery_boy_id
            )
            .first()
        )

    @staticmethod
    def get_all_by_delivery_boy(db: Session, delivery_boy_id, against: str = None, status: str = None):
        query = (
            db.query(DeliveryBoyComplaint)
            .filter(DeliveryBoyComplaint.delivery_boy_reference_id == delivery_boy_id)
        )
        if against:
            query = query.filter(DeliveryBoyComplaint.against == against)
        if status:
            query = query.filter(DeliveryBoyComplaint.status == status)
        return query.order_by(DeliveryBoyComplaint.created_at.desc()).all()

    @staticmethod
    def update(db: Session, complaint: DeliveryBoyComplaint, data: dict) -> DeliveryBoyComplaint:
        for key, value in data.items():
            setattr(complaint, key, value)
        db.flush()
        db.refresh(complaint)
        return complaint

    @staticmethod
    def withdraw(db: Session, complaint: DeliveryBoyComplaint) -> DeliveryBoyComplaint:
        complaint.status = "closed"
        db.flush()
        db.refresh(complaint)
        return complaint
