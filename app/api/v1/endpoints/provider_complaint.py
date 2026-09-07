from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_provider
from app.services.provider_complaint_service import ProviderComplaintService
from app.schemas.provider_complaint_schema import (
    RaiseProviderComplaintRequest,
    UpdateProviderComplaintRequest,
    ProviderComplaintResponse,
    ProviderComplaintListResponse,
)

router = APIRouter()


@router.post(
    "",
    summary="Raise a Provider Complaint",
    description=(
        "**Submit a complaint against the platform or a delivery boy.**\n\n"
        "Set `against` to `platform` for billing / feature issues, or `delivery_boy` "
        "for delivery-related problems. Optionally link a `delivery_boy_id`.\n\n"
        "**When to call:** When the provider encounters a problem via the support section.\n\n"
        "**Flow:** `POST /provider/complaint` → `GET /provider/complaint` to track status"
    )
)
def raise_complaint(
    payload: RaiseProviderComplaintRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderComplaintService.raise_complaint(
        db,
        provider_id=current_provider["provider_id"],
        payload=payload
    )


@router.get(
    "",
    response_model=ProviderComplaintListResponse,
    summary="List My Complaints",
    description=(
        "**Fetch all complaints raised by this provider.**\n\n"
        "Filter by `against` (`platform` or `delivery_boy`) and/or "
        "`status` (`open`, `in_progress`, `resolved`, `closed`, `rejected`).\n\n"
        "**When to call:** On the provider's support / complaint history screen."
    )
)
def get_my_complaints(
    against: Optional[str] = Query(
        None,
        description="Filter by complaint target: platform or delivery_boy"
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by status: open, in_progress, resolved, closed, rejected"
    ),
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderComplaintService.get_my_complaints(
        db,
        provider_id=current_provider["provider_id"],
        against=against,
        status=status
    )


@router.get(
    "/{complaint_id}",
    response_model=ProviderComplaintResponse,
    summary="Get Complaint Detail",
    description=(
        "**Fetch full details and admin response for a specific complaint.**\n\n"
        "Use `complaint_id` from `GET /provider/complaint`.\n\n"
        "**When to call:** When the provider taps a complaint to see updates or resolution."
    )
)
def get_complaint(
    complaint_id: UUID,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderComplaintService.get_complaint(
        db,
        provider_id=current_provider["provider_id"],
        complaint_id=complaint_id
    )


@router.put(
    "/{complaint_id}",
    summary="Update Complaint",
    description=(
        "**Edit the subject or description of an open complaint.**\n\n"
        "Only complaints with status `open` can be updated. "
        "Use `complaint_id` from the complaints list."
    )
)
def update_complaint(
    complaint_id: UUID,
    payload: UpdateProviderComplaintRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderComplaintService.update_complaint(
        db,
        provider_id=current_provider["provider_id"],
        complaint_id=complaint_id,
        payload=payload
    )


@router.delete(
    "/{complaint_id}",
    summary="Withdraw Complaint",
    description=(
        "**Withdraw (cancel) an open complaint.**\n\n"
        "The complaint is marked as `closed`. Use this if the issue was resolved informally."
    )
)
def withdraw_complaint(
    complaint_id: UUID,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderComplaintService.withdraw_complaint(
        db,
        provider_id=current_provider["provider_id"],
        complaint_id=complaint_id
    )
