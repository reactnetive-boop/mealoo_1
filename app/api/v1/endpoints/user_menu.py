from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.user_menu_schema import (
    UserPackageListResponse,
    UserPackageDetailResponse,
    ServiceabilityResponse,
)
from app.services.user_menu_service import UserMenuService

router = APIRouter()


@router.get(
    "/serviceability",
    response_model=ServiceabilityResponse,
    summary="Is this Pincode Served?",
    description=(
        "`status`: `ok`, `pincode_not_serviceable` (Orleeno does not operate there) or "
        "`no_kitchens` (served area but no kitchen is selling right now). Show the matching "
        "message instead of an empty menu."
    ),
)
def serviceability(
    pin_code: int = Query(..., ge=100000, le=999999),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return UserMenuService.serviceability(db, pin_code)


@router.get(
    "/packages",
    response_model=UserPackageListResponse,
    summary="Browse Meal Packages by Pincode",
    description=(
        "Only packages a customer can actually buy: approved, active and available packages "
        "from approved, active kitchens that are accepting orders and serve this (active) "
        "pincode. `provider_id` is the kitchen to order from."
    ),
)
def list_packages(
    pin_code: int = Query(..., ge=100000, le=999999, description="Delivery pincode"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return UserMenuService.list_packages(db, pin_code)


@router.get(
    "/packages/{package_id}",
    response_model=UserPackageDetailResponse,
    summary="Get Package Detail",
    description="Pass `provider_id` from the listing (required for Orleeno catalogue packages).",
)
def get_package(
    package_id: UUID,
    provider_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return UserMenuService.get_package(db, package_id, provider_id)
