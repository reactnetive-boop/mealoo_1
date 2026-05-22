from fastapi import (
    APIRouter,
    Depends
)

from sqlalchemy.orm import Session

from app.core.database import get_db

from app.schemas.menu_schema import (
    CreateMenuPackageRequest,
    MenuPackageResponse
)

from app.services.menu_service import (
    MenuService
)

from app.dependencies.auth_dependency import (
    get_current_provider
)

router = APIRouter()


@router.post(
    "/package",
    response_model=MenuPackageResponse
)
async def create_package(
    request: CreateMenuPackageRequest,
    db: Session = Depends(get_db),
    current_provider = Depends(
        get_current_provider
    )
):
    print(current_provider)
    response = (
        MenuService.create_package(
            db,
            str(
                current_provider['provider_id']
            ),
            request
        )
    )

    return response