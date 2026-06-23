from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from uuid import UUID

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.complaint_schema import (
    RaiseComplaintRequest,
    UpdateComplaintRequest,
    ComplaintResponse,
    ComplaintListResponse
)
from app.services.complaint_service import ComplaintService

router = APIRouter()


@router.post(
    "",
    summary="Raise a Complaint",
    description=(
        "**Submit a complaint about an order, delivery, or the platform.**\n\n"
        "Provide `subject`, `description`, and optionally link an `order_id` or `subscription_id`. "
        "Returns the complaint ID and initial status (`open`).\n\n"
        "**When to call:** When the user taps 'Report an Issue' on the order detail or support screen.\n\n"
        "**Flow:** `POST /user/complaint` → `GET /user/complaint` to track status"
    )
)
def raise_complaint(
    payload: RaiseComplaintRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ComplaintService.raise_complaint(
        db,
        current_user["user_id"],
        payload
    )


@router.get(
    "",
    response_model=ComplaintListResponse,
    summary="List My Complaints",
    description=(
        "**Fetch all complaints raised by the logged-in user.**\n\n"
        "Returns complaint subject, status (`open`, `in_progress`, `resolved`, `closed`), "
        "and timestamps. Use `complaint_id` to view details or update.\n\n"
        "**When to call:** On the 'My Complaints' / support history screen."
    )
)
def get_my_complaints(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ComplaintService.get_my_complaints(
        db,
        current_user["user_id"]
    )


@router.get(
    "/{complaint_id}",
    response_model=ComplaintResponse,
    summary="Get Complaint Detail",
    description=(
        "**Fetch full details of a specific complaint including admin response.**\n\n"
        "Use `complaint_id` from `GET /user/complaint`.\n\n"
        "**When to call:** When the user taps on a complaint to view its current status or resolution."
    )
)
def get_complaint(
    complaint_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ComplaintService.get_complaint(
        db,
        current_user["user_id"],
        complaint_id
    )


@router.put(
    "/{complaint_id}",
    summary="Update Complaint",
    description=(
        "**Edit the subject or description of an open complaint.**\n\n"
        "Only complaints with status `open` can be updated. "
        "Use `complaint_id` from the complaints list.\n\n"
        "**When to call:** When the user wants to add more details before an admin responds."
    )
)
def update_complaint(
    complaint_id: UUID,
    payload: UpdateComplaintRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ComplaintService.update_complaint(
        db,
        current_user["user_id"],
        complaint_id,
        payload
    )


@router.delete(
    "/{complaint_id}",
    summary="Withdraw Complaint",
    description=(
        "**Withdraw (cancel) an open complaint.**\n\n"
        "Use this if the user's issue was resolved informally or was raised by mistake. "
        "The complaint is marked as `closed`.\n\n"
        "**When to call:** When the user taps 'Withdraw' on an open complaint."
    )
)
def withdraw_complaint(
    complaint_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ComplaintService.withdraw_complaint(
        db,
        current_user["user_id"],
        complaint_id
    )
