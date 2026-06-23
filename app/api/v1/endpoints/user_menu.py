from fastapi import APIRouter, Depends, Query

from sqlalchemy.orm import Session

from uuid import UUID

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.user_menu_schema import (
    UserPackageListResponse,
    UserPackageDetailResponse
)
from app.services.user_menu_service import UserMenuService

router = APIRouter()


@router.get(
    "/packages",
    response_model=UserPackageListResponse,
    summary="Browse Meal Packages by Pincode",
    description=(
        "**Fetch all available meal packages offered by vendors in the user's area.**\n\n"
        "Pass the user's delivery pincode as a query parameter. "
        "Only packages from vendors who service that pincode and have marked themselves available are returned.\n\n"
        "Each item includes `package_id`, `provider_id`, pricing, meal type, and a primary image URL. "
        "Use `package_id` to fetch full details or add to cart.\n\n"
        "**When to call:** On the home/browse screen after the user sets their delivery location.\n\n"
        "**Flow:** Verify pincode (`POST /location/verify-pincode`) → "
        "`GET /user/menu/packages?pin_code=...` → select a package → "
        "`GET /user/menu/packages/{package_id}` for full details"
    )
)
def list_packages(
    pin_code: int = Query(
        ...,
        description="Pincode to filter providers in your area"
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return UserMenuService.list_packages(
        db,
        pin_code
    )


@router.get(
    "/packages/{package_id}",
    response_model=UserPackageDetailResponse,
    summary="Get Package Detail",
    description=(
        "**Fetch complete details of a single meal package.**\n\n"
        "Returns package name, description, meal items list, all images, pricing, "
        "subscription availability, and food type (veg/non-veg).\n\n"
        "**When to call:** When the user taps on a package card from the listing screen.\n\n"
        "**Flow:** `GET /user/menu/packages` → tap package → "
        "`GET /user/menu/packages/{package_id}` → add to cart or subscribe"
    )
)
def get_package(
    package_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return UserMenuService.get_package(
        db,
        package_id
    )
