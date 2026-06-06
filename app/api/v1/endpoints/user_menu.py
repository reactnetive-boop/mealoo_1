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
    response_model=UserPackageListResponse
)
def list_packages(
    category_id: UUID = Query(
        ...,
        description="Category UUID to filter packages"
    ),
    pin_code: int = Query(
        ...,
        description="Pincode to filter providers in your area"
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return UserMenuService.list_packages(
        db,
        category_id,
        pin_code
    )


@router.get(
    "/packages/{package_id}",
    response_model=UserPackageDetailResponse
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
