from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.provider_complaint_repository import ProviderComplaintRepository

EDITABLE_STATUSES = {"open"}


class ProviderComplaintService:

    @staticmethod
    def raise_complaint(db: Session, provider_id: str, payload):
        data = payload.model_dump()
        data["delivery_boy_reference_id"] = data.pop("delivery_boy_id", None)
        data["provider_reference_id"] = provider_id
        data["status"] = "open"

        complaint = ProviderComplaintRepository.create(db, data)

        return {
            "success": True,
            "message": "Complaint raised successfully",
            "complaint_id": str(complaint.provider_complaint_id)
        }

    @staticmethod
    def get_my_complaints(
        db: Session,
        provider_id: str,
        against: str = None,
        status: str = None
    ):
        complaints = ProviderComplaintRepository.get_all_by_provider(
            db, provider_id, against=against, status=status
        )
        return {
            "success": True,
            "total": len(complaints),
            "complaints": complaints
        }

    @staticmethod
    def get_complaint(db: Session, provider_id: str, complaint_id):
        complaint = ProviderComplaintRepository.get_by_id_and_provider(
            db, complaint_id, provider_id
        )
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return complaint

    @staticmethod
    def update_complaint(db: Session, provider_id: str, complaint_id, payload):
        complaint = ProviderComplaintRepository.get_by_id_and_provider(
            db, complaint_id, provider_id
        )
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")

        if complaint.status not in EDITABLE_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Complaint cannot be edited in '{complaint.status}' status"
            )

        update_data = payload.model_dump(exclude_unset=True)
        ProviderComplaintRepository.update(db, complaint, update_data)

        return {
            "success": True,
            "message": "Complaint updated successfully",
            "complaint_id": str(complaint.provider_complaint_id)
        }

    @staticmethod
    def withdraw_complaint(db: Session, provider_id: str, complaint_id):
        complaint = ProviderComplaintRepository.get_by_id_and_provider(
            db, complaint_id, provider_id
        )
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")

        if complaint.status not in EDITABLE_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Complaint cannot be withdrawn in '{complaint.status}' status"
            )

        ProviderComplaintRepository.withdraw(db, complaint)

        return {
            "success": True,
            "message": "Complaint withdrawn successfully"
        }
