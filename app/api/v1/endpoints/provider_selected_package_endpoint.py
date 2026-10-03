from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_provider
from app.schemas.provider_selected_package_schema import (
    SelectPackageRequest,
    UpdateCapacityRequest,
    UpdateCapacityResponse,
)
from app.services.menu_service import MenuService

router = APIRouter()


def _same_kitchen(provider_id, current) -> None:
    # Older app versions send provider_id; it must match the session
    if provider_id is not None and str(provider_id) != current["provider_id"]:
        raise HTTPException(status_code=403, detail="You can only manage your own kitchen")


@router.post(
    "/select",
    summary="Offer an Orleeno Catalogue Package",
    description="Adds a live catalogue package to the kitchen's menu (optionally with a daily capacity).",
)
def select_package(
    request: SelectPackageRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    _same_kitchen(request.provider_id, current_provider)
    return MenuService.select_catalog_package(
        db, current_provider["provider_id"], request.package_id, request.daily_capacity
    )


@router.delete("/select/{package_id}", summary="Stop Offering a Catalogue Package")
def unselect_package(
    package_id: UUID,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return MenuService.unselect_catalog_package(db, current_provider["provider_id"], package_id)


@router.get(
    "/capacity",
    response_model=UpdateCapacityResponse,
    summary="Get Daily Package Capacity",
)
def get_package_capacity(
    package_id: UUID,
    provider_id: UUID | None = None,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    _same_kitchen(provider_id, current_provider)
    return MenuService.get_capacity(db, current_provider["provider_id"], package_id)


@router.put(
    "/capacity",
    response_model=UpdateCapacityResponse,
    summary="Set Daily Package Capacity",
    description="Cannot go below what is already booked for an upcoming day. null removes the limit.",
)
def update_package_capacity(
    request: UpdateCapacityRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    _same_kitchen(request.provider_id, current_provider)
    return MenuService.set_capacity(db, current_provider["provider_id"], request.package_id, request.daily_capacity)
