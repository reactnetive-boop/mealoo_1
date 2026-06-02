from fastapi import (
    APIRouter,
    Depends
)

from sqlalchemy.orm import Session

from app.core.database import get_db

from app.schemas.menu_schema import (
    GetMenuCategoryListResponse,
    CreateMenuPackageRequest,
    MenuPackageResponse,
    GetMenuPackageResponse,
    UpdateMenuPackageRequest,
    CommonResponse
)

from app.services.menu_service import (
    MenuService
)
from app.services.menu_category_service import (
    MenuCategoryService
)
from app.dependencies.auth_dependency import (
    get_current_provider
)
from uuid import UUID

router = APIRouter()

@router.get(
    "/categories",
    response_model=GetMenuCategoryListResponse
)

async def get_menu_categories(
    db: Session = Depends(get_db)
):

    categories = (
        MenuCategoryService
        .get_menu_categories(
            db=db
        )
    )

    return {
        "success": True,
        "message": (
            "Menu categories fetched successfully"
        ),
        "data": categories
    }

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

@router.get(
    "/get/{package_id}",
    response_model=GetMenuPackageResponse
)
def get_package(
    package_id: UUID,
    db: Session = Depends(get_db)
):

    return MenuService.get_package_details(
        db,
        package_id
    )

@router.get(
    "/list/{provider_id}"
)
def list_packages(
    provider_id: str,
    db: Session = Depends(get_db)
):

    return MenuService.list_provider_packages(
        db,
        provider_id
    )

@router.put(
"/update/{package_id}",
response_model=CommonResponse
)
def update_package(
    package_id: UUID,
    request: UpdateMenuPackageRequest,
    db: Session = Depends(get_db)
):

    MenuService.update_package(
        db,
        package_id,
        request
    )

    return {
        "success": True,
        "message": "Package updated successfully"
    }

@router.delete(
    "/delete/{package_id}",
    response_model=CommonResponse
)
def delete_package(
    package_id: UUID,
    db: Session = Depends(get_db)
):

    return MenuService.delete_package(
        db,
        package_id
    )
    