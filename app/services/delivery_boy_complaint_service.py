from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.delivery_boy_complaint_repository import DeliveryBoyComplaintRepository

EDITABLE_STATUSES = {"open"}


class DeliveryBoyComplaintService:

    @staticmethod
    def raise_complaint(db: Session, delivery_boy_id: str, payload):
        data = payload.model_dump()
        data["provider_reference_id"] = data.pop("provider_id", None)
        data["delivery_boy_reference_id"] = delivery_boy_id
        data["status"] = "open"

        complaint = DeliveryBoyComplaintRepository.create(db, data)

        return {
            "success": True,
            "message": "Complaint raised successfully",
            "complaint_id": str(complaint.delivery_boy_complaint_id)
        }

    @staticmethod
    def get_my_complaints(
        db: Session,
        delivery_boy_id: str,
        against: str = None,
        status: str = None
    ):
        complaints = DeliveryBoyComplaintRepository.get_all_by_delivery_boy(
            db, delivery_boy_id, against=against, status=status
        )
        return {
            "success": True,
            "total": len(complaints),
            "complaints": complaints
        }

    @staticmethod
    def get_complaint(db: Session, delivery_boy_id: str, complaint_id):
        complaint = DeliveryBoyComplaintRepository.get_by_id_and_delivery_boy(
            db, complaint_id, delivery_boy_id
        )
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return complaint

    @staticmethod
    def update_complaint(db: Session, delivery_boy_id: str, complaint_id, payload):
        complaint = DeliveryBoyComplaintRepository.get_by_id_and_delivery_boy(
            db, complaint_id, delivery_boy_id
        )
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")

        if complaint.status not in EDITABLE_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Complaint cannot be edited in '{complaint.status}' status"
            )

        update_data = payload.model_dump(exclude_unset=True)
        DeliveryBoyComplaintRepository.update(db, complaint, update_data)

        return {
            "success": True,
            "message": "Complaint updated successfully",
            "complaint_id": str(complaint.delivery_boy_complaint_id)
        }

    @staticmethod
    def withdraw_complaint(db: Session, delivery_boy_id: str, complaint_id):
        complaint = DeliveryBoyComplaintRepository.get_by_id_and_delivery_boy(
            db, complaint_id, delivery_boy_id
        )
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")

        if complaint.status not in EDITABLE_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Complaint cannot be withdrawn in '{complaint.status}' status"
            )

        DeliveryBoyComplaintRepository.withdraw(db, complaint)

        return {
            "success": True,
            "message": "Complaint withdrawn successfully"
        }
