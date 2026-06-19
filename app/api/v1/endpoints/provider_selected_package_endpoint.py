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


@router.post("/select")
def select_package(
    request: SelectPackageRequest,
    db: Session = Depends(get_db)
):
    return ProviderSelectedPackageService.select_package(db=db, request=request)


@router.put(
    "/capacity",
    response_model=UpdateCapacityResponse
)
def update_package_capacity(
    request: UpdateCapacityRequest,
    db: Session = Depends(get_db)
):
    """
    Set or update the daily capacity for a provider-package pair.
    Send daily_capacity=null to remove the limit.
    Rejects if the new limit would undercut active subscription demand.
    """
    return ProviderSelectedPackageService.update_capacity(db=db, request=request)