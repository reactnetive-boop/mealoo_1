from uuid import UUID

from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.core.database import get_db

from app.schemas.provider_selected_package_schema import (
    SelectPackageRequest,
    UpdateCapacityRequest,
    UpdateCapacityResponse,
)

from app.services.provider_selected_package_service import (
    ProviderSelectedPackageService
)

router = APIRouter()


@router.post(
    "/select",
    summary="Select a Package to Offer",
    description=(
        "**Add a meal package to the provider's active offering.**\n\n"
        "After creating a package, the provider must explicitly select it to make it visible "
        "to users in their area. Requires `provider_id` and `package_id`.\n\n"
        "**When to call:** After `POST /menu/package` or when the provider wants to start offering "
        "an existing package.\n\n"
        "**Flow:** `POST /menu/package` → `POST /provider/packages/select` → "
        "package appears in `GET /user/menu/packages`"
    )
)
def select_package(
    request: SelectPackageRequest,
    db: Session = Depends(get_db)
):
    return ProviderSelectedPackageService.select_package(db=db, request=request)


@router.get(
    "/capacity",
    response_model=UpdateCapacityResponse,
    summary="Get Daily Package Capacity",
    description=(
        "**Fetch the current daily capacity for a provider-package pair.**\n\n"
        "`daily_capacity` is null when no limit is set. `current_peak_demand` is the highest "
        "per-meal-slot demand from active subscriptions — the lowest value the capacity can be "
        "set to.\n\n"
        "**When to call:** On the provider's package detail screen, to show the current limit."
    )
)
def get_package_capacity(
    provider_id: UUID,
    package_id: UUID,
    db: Session = Depends(get_db)
):
    return ProviderSelectedPackageService.get_capacity(
        db=db, provider_id=provider_id, package_id=package_id
    )


@router.put(
    "/capacity",
    response_model=UpdateCapacityResponse,
    summary="Set Daily Package Capacity",
    description=(
        "**Set or update the maximum daily order limit for a provider-package pair.**\n\n"
        "Use this to prevent over-subscription. For example, a kitchen can cap a package at "
        "50 servings per day per meal slot.\n\n"
        "Send `daily_capacity=null` to remove the limit entirely.\n\n"
        "**Validation:** The system rejects a new capacity that is lower than the current number "
        "of active subscriptions already consuming that package.\n\n"
        "**When to call:** During package setup or when the provider needs to limit orders due to "
        "kitchen capacity changes."
    )
)
def update_package_capacity(
    request: UpdateCapacityRequest,
    db: Session = Depends(get_db)
):
    return ProviderSelectedPackageService.update_capacity(db=db, request=request)
