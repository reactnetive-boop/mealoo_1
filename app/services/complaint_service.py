from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.repositories.complaint_repository import ComplaintRepository

# Statuses that allow user edits
EDITABLE_STATUSES = {"open"}


class ComplaintService:

    @staticmethod
    def raise_complaint(
        db: Session,
        user_id: str,
        payload
    ):

        complaint_data = payload.model_dump()

        # Schema field names → renamed model columns
        complaint_data["vendor_reference_id"] = complaint_data.pop("vendor_id", None)
        complaint_data["order_reference_id"] = complaint_data.pop("order_id", None)
        complaint_data["subscription_reference_id"] = complaint_data.pop("subscription_id", None)

        complaint_data["user_reference_id"] = user_id

        complaint_data["status"] = "open"

        complaint = ComplaintRepository.create(
            db, complaint_data
        )

        return {
            "success": True,
            "message": "Complaint raised successfully",
            "complaint_id": str(complaint.complaint_id)
        }

    @staticmethod
    def get_my_complaints(
        db: Session,
        user_id: str
    ):

        complaints = ComplaintRepository.get_all_by_user(
            db, user_id
        )

        return {
            "success": True,
            "total": len(complaints),
            "complaints": complaints
        }

    @staticmethod
    def get_complaint(
        db: Session,
        user_id: str,
        complaint_id
    ):

        complaint = ComplaintRepository.get_by_id(
            db, complaint_id
        )

        if not complaint:

            raise HTTPException(
                status_code=404,
                detail="Complaint not found"
            )

        if str(complaint.user_reference_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        return complaint

    @staticmethod
    def update_complaint(
        db: Session,
        user_id: str,
        complaint_id,
        payload
    ):

        complaint = ComplaintRepository.get_by_id(
            db, complaint_id
        )

        if not complaint:

            raise HTTPException(
                status_code=404,
                detail="Complaint not found"
            )

        if str(complaint.user_reference_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        if complaint.status not in EDITABLE_STATUSES:

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Complaint cannot be edited. "
                    f"Current status: {complaint.status}"
                )
            )

        update_data = payload.model_dump(exclude_unset=True)

        updated = ComplaintRepository.update(
            db, complaint, update_data
        )

        return {
            "success": True,
            "message": "Complaint updated successfully",
            "complaint_id": str(updated.complaint_id)
        }

    @staticmethod
    def withdraw_complaint(
        db: Session,
        user_id: str,
        complaint_id
    ):

        complaint = ComplaintRepository.get_by_id(
            db, complaint_id
        )

        if not complaint:

            raise HTTPException(
                status_code=404,
                detail="Complaint not found"
            )

        if str(complaint.user_reference_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        if complaint.status not in EDITABLE_STATUSES:

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Complaint cannot be withdrawn. "
                    f"Current status: {complaint.status}"
                )
            )

        ComplaintRepository.withdraw(db, complaint)

        return {
            "success": True,
            "message": "Complaint withdrawn successfully"
        }
