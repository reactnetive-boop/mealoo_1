from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_delivery_boy_service import AdminDeliveryBoyService
from app.schemas.admin_schema import AdminUpdateDeliveryBoyRequest

router = APIRouter()


@router.get(
    "",
    summary="List All Delivery Boys",
    description=(
        "**Fetch a paginated list of all registered delivery personnel.**\n\n"
        "Filter by `search` (name or mobile), `is_active`, and/or `provider_id` to see "
        "delivery boys assigned to a specific vendor.\n\n"
        "**When to call:** On the admin delivery management screen or when assigning a new delivery boy to a provider."
    )
)
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


@router.get(
    "/{delivery_boy_id}",
    summary="Get Delivery Boy Detail",
    description=(
        "**Fetch full profile and delivery statistics for a specific delivery boy.**\n\n"
        "Returns assigned provider, active status, and order completion summary. "
        "Use `delivery_boy_id` (UUID) from the delivery boys list."
    )
)
def get_delivery_boy_detail(
    delivery_boy_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.get_delivery_boy_detail(db, str(delivery_boy_id))


@router.put(
    "/{delivery_boy_id}",
    summary="Update Delivery Boy Details",
    description=(
        "**Edit a delivery boy's name, active status, or other profile fields.**\n\n"
        "Use for admin-side corrections or to deactivate a delivery boy. "
        "To reassign to a different provider, use `PUT /{delivery_boy_id}/assign-provider` instead."
    )
)
def update_delivery_boy(
    delivery_boy_id: UUID,
    payload: AdminUpdateDeliveryBoyRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.update_delivery_boy(db, str(delivery_boy_id), payload)


@router.put(
    "/{delivery_boy_id}/assign-provider",
    summary="Assign Delivery Boy to a Provider",
    description=(
        "**Link a delivery boy to a specific vendor/provider.**\n\n"
        "Pass `provider_id` as a query parameter. The delivery boy will then appear in that provider's "
        "delivery team and can be assigned to that provider's orders.\n\n"
        "**When to call:** During onboarding of a new delivery boy, or when reassigning between providers."
    )
)
def assign_provider(
    delivery_boy_id: UUID,
    provider_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.assign_provider(db, str(delivery_boy_id), str(provider_id))
