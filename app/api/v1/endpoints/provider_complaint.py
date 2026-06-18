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


@router.post("")
def raise_complaint(
    payload: RaiseProviderComplaintRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderComplaintService.raise_complaint(
        db,
        provider_id=current_provider.provider_id,
        payload=payload
    )


@router.get("", response_model=ProviderComplaintListResponse)
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
        provider_id=current_provider.provider_id,
        against=against,
        status=status
    )


@router.get("/{complaint_id}", response_model=ProviderComplaintResponse)
def get_complaint(
    complaint_id: UUID,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderComplaintService.get_complaint(
        db,
        provider_id=current_provider.provider_id,
        complaint_id=complaint_id
    )


@router.put("/{complaint_id}")
def update_complaint(
    complaint_id: UUID,
    payload: UpdateProviderComplaintRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderComplaintService.update_complaint(
        db,
        provider_id=current_provider.provider_id,
        complaint_id=complaint_id,
        payload=payload
    )


@router.delete("/{complaint_id}")
def withdraw_complaint(
    complaint_id: UUID,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderComplaintService.withdraw_complaint(
        db,
        provider_id=current_provider.provider_id,
        complaint_id=complaint_id
    )
