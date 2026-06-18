from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.complaint_model import Complaint
from app.models.provider_complaint_model import ProviderComplaint

VALID_RESOLUTIONS = {"in_progress", "resolved", "rejected", "closed"}


class AdminComplaintService:

    @staticmethod
    def list_all_complaints(db: Session, complaint_type: str = None, status: str = None,
                            against: str = None, page: int = 1, limit: int = 20):
        results = []

        if complaint_type in (None, "user"):
            q = db.query(Complaint)
            if status:
                q = q.filter(Complaint.status == status)
            if against:
                q = q.filter(Complaint.against == against)
            for c in q.all():
                results.append({
                    "id": c.id,
                    "complainant_type": "user",
                    "complainant_id": c.user_id,
                    "against": c.against,
                    "status": c.status,
                    "subject": c.subject,
                    "created_at": c.created_at,
                })

        if complaint_type in (None, "provider"):
            q = db.query(ProviderComplaint)
            if status:
                q = q.filter(ProviderComplaint.status == status)
            if against:
                q = q.filter(ProviderComplaint.against == against)
            for c in q.all():
                results.append({
                    "id": c.id,
                    "complainant_type": "provider",
                    "complainant_id": c.provider_id,
                    "against": c.against,
                    "status": c.status,
                    "subject": c.subject,
                    "created_at": c.created_at,
                })

        results.sort(key=lambda x: x["created_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        total = len(results)
        offset = (page - 1) * limit
        paged = results[offset: offset + limit]

        return {"success": True, "total": total, "complaints": paged}

    @staticmethod
    def get_user_complaint(db: Session, complaint_id: str):
        complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint:
            raise HTTPException(status_code=404, detail="User complaint not found")
        return complaint

    @staticmethod
    def get_provider_complaint(db: Session, complaint_id: str):
        complaint = db.query(ProviderComplaint).filter(ProviderComplaint.id == complaint_id).first()
        if not complaint:
            raise HTTPException(status_code=404, detail="Provider complaint not found")
        return complaint

    @staticmethod
    def resolve_user_complaint(db: Session, complaint_id: str, payload, admin_id: str):
        if payload.status not in VALID_RESOLUTIONS:
            raise HTTPException(status_code=400, detail=f"Invalid status: {', '.join(VALID_RESOLUTIONS)}")

        complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        if complaint.status in ("resolved", "closed", "rejected"):
            raise HTTPException(status_code=400, detail=f"Complaint is already '{complaint.status}'")

        complaint.status = payload.status
        if payload.admin_notes:
            complaint.admin_notes = payload.admin_notes
        if payload.resolution:
            complaint.resolution = payload.resolution
        if payload.status in ("resolved", "closed", "rejected"):
            complaint.resolved_by = admin_id
            complaint.resolved_at = datetime.now(timezone.utc)
        db.commit()

        return {"success": True, "message": f"Complaint status updated to '{payload.status}'"}

    @staticmethod
    def resolve_provider_complaint(db: Session, complaint_id: str, payload, admin_id: str):
        if payload.status not in VALID_RESOLUTIONS:
            raise HTTPException(status_code=400, detail=f"Invalid status: {', '.join(VALID_RESOLUTIONS)}")

        complaint = db.query(ProviderComplaint).filter(ProviderComplaint.id == complaint_id).first()
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        if complaint.status in ("resolved", "closed", "rejected"):
            raise HTTPException(status_code=400, detail=f"Complaint is already '{complaint.status}'")

        complaint.status = payload.status
        if payload.admin_notes:
            complaint.admin_notes = payload.admin_notes
        if payload.resolution:
            complaint.resolution = payload.resolution
        if payload.status in ("resolved", "closed", "rejected"):
            complaint.resolved_by = admin_id
            complaint.resolved_at = datetime.now(timezone.utc)
        db.commit()

        return {"success": True, "message": f"Complaint status updated to '{payload.status}'"}
