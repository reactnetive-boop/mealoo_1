from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_complaint_service import AdminComplaintService
from app.schemas.admin_schema import AdminResolveComplaintRequest

router = APIRouter()


@router.get("")
def list_all_complaints(
    complaint_type: Optional[str] = Query(None, description="user or provider"),
    status: Optional[str] = Query(None),
    against: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminComplaintService.list_all_complaints(
        db, complaint_type=complaint_type, status=status, against=against, page=page, limit=limit
    )


@router.get("/user/{complaint_id}")
def get_user_complaint(
    complaint_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminComplaintService.get_user_complaint(db, str(complaint_id))


@router.get("/provider/{complaint_id}")
def get_provider_complaint(
    complaint_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminComplaintService.get_provider_complaint(db, str(complaint_id))


@router.put("/user/{complaint_id}/resolve")
def resolve_user_complaint(
    complaint_id: UUID,
    payload: AdminResolveComplaintRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminComplaintService.resolve_user_complaint(db, str(complaint_id), payload, current["admin_id"])


@router.put("/provider/{complaint_id}/resolve")
def resolve_provider_complaint(
    complaint_id: UUID,
    payload: AdminResolveComplaintRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminComplaintService.resolve_provider_complaint(db, str(complaint_id), payload, current["admin_id"])
