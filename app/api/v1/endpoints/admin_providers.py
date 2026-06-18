from typing import Optional
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_provider_service import AdminProviderService
from app.schemas.admin_schema import (
    AdminUpdateProviderRequest,
    AdminWalletAdjustRequest,
    AdminMarkUnavailabilityRequest,
)

router = APIRouter()


@router.get("")
def list_providers(
    search: Optional[str] = Query(None),
    pincode: Optional[int] = Query(None),
    is_profile_completed: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.list_providers(
        db, search=search, pincode=pincode,
        is_profile_completed=is_profile_completed, page=page, limit=limit
    )


@router.get("/{provider_id}")
def get_provider_detail(
    provider_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.get_provider_detail(db, str(provider_id))


@router.put("/{provider_id}")
def update_provider(
    provider_id: UUID,
    payload: AdminUpdateProviderRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.update_provider(db, str(provider_id), payload)


@router.put("/{provider_id}/activate")
def activate_provider(
    provider_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.set_provider_active(db, str(provider_id), True)


@router.put("/{provider_id}/deactivate")
def deactivate_provider(
    provider_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.set_provider_active(db, str(provider_id), False)


@router.post("/{provider_id}/wallet/adjust")
def adjust_provider_wallet(
    provider_id: UUID,
    payload: AdminWalletAdjustRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.adjust_wallet(db, str(provider_id), payload, current["admin_id"])


@router.put("/{provider_id}/accepting-orders")
def set_accepting_orders(
    provider_id: UUID,
    accepting: bool = Query(..., description="true to enable, false to disable"),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.toggle_accepting_orders(db, str(provider_id), accepting)


@router.get("/{provider_id}/unavailability")
def list_unavailability(
    provider_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.list_unavailability(db, str(provider_id))


@router.post("/{provider_id}/unavailability")
def mark_unavailable(
    provider_id: UUID,
    payload: AdminMarkUnavailabilityRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.mark_unavailable(db, str(provider_id), payload)


@router.delete("/{provider_id}/unavailability/{unavailable_date}")
def remove_unavailability(
    provider_id: UUID,
    unavailable_date: date,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.remove_unavailability(db, str(provider_id), unavailable_date)
