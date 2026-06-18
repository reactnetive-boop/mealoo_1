from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_delivery_boy_service import AdminDeliveryBoyService
from app.schemas.admin_schema import AdminUpdateDeliveryBoyRequest

router = APIRouter()


@router.get("")
def list_delivery_boys(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    provider_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.list_delivery_boys(
        db, search=search, is_active=is_active,
        provider_id=str(provider_id) if provider_id else None,
        page=page, limit=limit
    )


@router.get("/{delivery_boy_id}")
def get_delivery_boy_detail(
    delivery_boy_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.get_delivery_boy_detail(db, str(delivery_boy_id))


@router.put("/{delivery_boy_id}")
def update_delivery_boy(
    delivery_boy_id: UUID,
    payload: AdminUpdateDeliveryBoyRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.update_delivery_boy(db, str(delivery_boy_id), payload)


@router.put("/{delivery_boy_id}/assign-provider")
def assign_provider(
    delivery_boy_id: UUID,
    provider_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.assign_provider(db, str(delivery_boy_id), str(provider_id))
