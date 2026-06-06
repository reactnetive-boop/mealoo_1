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


@router.post("")
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
    response_model=ComplaintListResponse
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
    response_model=ComplaintResponse
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


@router.put("/{complaint_id}")
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


@router.delete("/{complaint_id}")
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
