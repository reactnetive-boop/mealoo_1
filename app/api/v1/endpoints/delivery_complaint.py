from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_delivery_boy
from app.services.delivery_boy_complaint_service import DeliveryBoyComplaintService
from app.schemas.delivery_boy_complaint_schema import (
    RaiseDeliveryBoyComplaintRequest,
    UpdateDeliveryBoyComplaintRequest,
    DeliveryBoyComplaintResponse,
    DeliveryBoyComplaintListResponse,
)

router = APIRouter()


@router.post(
    "",
    summary="Raise a Delivery Boy Complaint",
    description=(
        "**Submit a complaint against the platform or a provider.**\n\n"
        "Set `against` to `platform` for app / payout issues, or `provider` "
        "for kitchen-related problems. Optionally link a `provider_id`.\n\n"
        "**When to call:** When the delivery boy encounters a problem via the support section.\n\n"
        "**Flow:** `POST /delivery/complaint` → `GET /delivery/complaint` to track status"
    )
)
def raise_complaint(
    payload: RaiseDeliveryBoyComplaintRequest,
    db: Session = Depends(get_db),
    current_delivery_boy=Depends(get_current_delivery_boy)
):
    return DeliveryBoyComplaintService.raise_complaint(
        db,
        delivery_boy_id=current_delivery_boy["delivery_boy_id"],
        payload=payload
    )


@router.get(
    "",
    response_model=DeliveryBoyComplaintListResponse,
    summary="List My Complaints",
    description=(
        "**Fetch all complaints raised by this delivery boy.**\n\n"
        "Filter by `against` (`platform` or `provider`) and/or "
        "`status` (`open`, `in_progress`, `resolved`, `closed`, `rejected`).\n\n"
        "**When to call:** On the delivery boy's support / complaint history screen."
    )
)
def get_my_complaints(
    against: Optional[str] = Query(
        None,
        description="Filter by complaint target: platform or provider"
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by status: open, in_progress, resolved, closed, rejected"
    ),
    db: Session = Depends(get_db),
    current_delivery_boy=Depends(get_current_delivery_boy)
):
    return DeliveryBoyComplaintService.get_my_complaints(
        db,
        delivery_boy_id=current_delivery_boy["delivery_boy_id"],
        against=against,
        status=status
    )


@router.get(
    "/{complaint_id}",
    response_model=DeliveryBoyComplaintResponse,
    summary="Get Complaint Detail",
    description=(
        "**Fetch full details and admin response for a specific complaint.**\n\n"
        "Use `complaint_id` from `GET /delivery/complaint`.\n\n"
        "**When to call:** When the delivery boy taps a complaint to see updates or resolution."
    )
)
def get_complaint(
    complaint_id: UUID,
    db: Session = Depends(get_db),
    current_delivery_boy=Depends(get_current_delivery_boy)
):
    return DeliveryBoyComplaintService.get_complaint(
        db,
        delivery_boy_id=current_delivery_boy["delivery_boy_id"],
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
    payload: UpdateDeliveryBoyComplaintRequest,
    db: Session = Depends(get_db),
    current_delivery_boy=Depends(get_current_delivery_boy)
):
    return DeliveryBoyComplaintService.update_complaint(
        db,
        delivery_boy_id=current_delivery_boy["delivery_boy_id"],
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
    current_delivery_boy=Depends(get_current_delivery_boy)
):
    return DeliveryBoyComplaintService.withdraw_complaint(
        db,
        delivery_boy_id=current_delivery_boy["delivery_boy_id"],
        complaint_id=complaint_id
    )
