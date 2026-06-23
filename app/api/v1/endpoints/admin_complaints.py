from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_complaint_service import AdminComplaintService
from app.schemas.admin_schema import AdminResolveComplaintRequest

router = APIRouter()


@router.get(
    "",
    summary="List All Complaints",
    description=(
        "**Fetch a paginated list of all complaints — both from users and providers.**\n\n"
        "Filter by:\n"
        "- `complaint_type`: `user` or `provider`\n"
        "- `status`: `open`, `in_progress`, `resolved`, `closed`, `rejected`\n"
        "- `against`: `platform`, `delivery_boy`, or `provider`\n\n"
        "**When to call:** On the admin complaints management screen. "
        "Focus on `open` and `in_progress` complaints that need action."
    )
)
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


@router.get(
    "/user/{complaint_id}",
    summary="Get User Complaint Detail",
    description=(
        "**Fetch full details of a complaint raised by a user.**\n\n"
        "Returns subject, description, linked order/subscription, status, and any prior admin responses. "
        "Use `complaint_id` from the complaints list."
    )
)
def get_user_complaint(
    complaint_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminComplaintService.get_user_complaint(db, str(complaint_id))


@router.get(
    "/provider/{complaint_id}",
    summary="Get Provider Complaint Detail",
    description=(
        "**Fetch full details of a complaint raised by a provider.**\n\n"
        "Returns the complaint target (platform or delivery boy), description, and status. "
        "Use `complaint_id` from the complaints list."
    )
)
def get_provider_complaint(
    complaint_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminComplaintService.get_provider_complaint(db, str(complaint_id))


@router.put(
    "/user/{complaint_id}/resolve",
    summary="Resolve User Complaint",
    description=(
        "**Update the status and add an admin response to a user complaint.**\n\n"
        "Set `status` to `resolved`, `rejected`, or `closed` and provide a `resolution_note` "
        "that will be visible to the user.\n\n"
        "**Flow:** View complaint → take action (refund, reassign, etc.) → resolve with a note"
    )
)
def resolve_user_complaint(
    complaint_id: UUID,
    payload: AdminResolveComplaintRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminComplaintService.resolve_user_complaint(db, str(complaint_id), payload, current["admin_id"])


@router.put(
    "/provider/{complaint_id}/resolve",
    summary="Resolve Provider Complaint",
    description=(
        "**Update the status and add an admin response to a provider complaint.**\n\n"
        "Set `status` to `resolved`, `rejected`, or `closed` and provide a `resolution_note` "
        "that will be visible to the provider."
    )
)
def resolve_provider_complaint(
    complaint_id: UUID,
    payload: AdminResolveComplaintRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminComplaintService.resolve_provider_complaint(db, str(complaint_id), payload, current["admin_id"])
