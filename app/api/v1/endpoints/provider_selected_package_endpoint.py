from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session

from app.core.database import get_db

from app.schemas.provider_selected_package_schema import (
    SelectPackageRequest
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
    return (
        ProviderSelectedPackageService
        .select_package(
            db=db,
            request=request
        )
    )