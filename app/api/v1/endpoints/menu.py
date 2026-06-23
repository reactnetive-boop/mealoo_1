from fastapi import (
    APIRouter,
    Depends,
    Query
)

from sqlalchemy.orm import Session

from app.core.database import get_db

from app.schemas.menu_schema import (
    GetMenuCategoryListResponse,
    MenuCategoryResponse,
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
    response_model=GetMenuCategoryListResponse,
    summary="List All Menu Categories",
    description=(
        "**Fetch all available food categories (e.g. South Indian, North Indian, Biryani).**\n\n"
        "Use this to populate the category picker when a provider is creating a new meal package. "
        "Each category has a `category_id` required in `POST /menu/package`.\n\n"
        "**No authentication required.** Can also be used on the user-facing filter/browse screen."
    )
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


@router.get(
    "/categories/{category_id}",
    response_model=MenuCategoryResponse,
    summary="Get Category Detail",
    description=(
        "**Fetch details of a single food category by its ID.**\n\n"
        "Returns category name and description. Use `category_id` from `GET /menu/categories`."
    )
)
async def get_menu_category(
    category_id: UUID,
    db: Session = Depends(get_db)
):

    return (
        MenuCategoryService
        .get_category(
            db=db,
            category_id=category_id
        )
    )


@router.post(
    "/package",
    response_model=MenuPackageResponse,
    summary="Create a Meal Package",
    description=(
        "**Create a new meal package under the logged-in provider's account.**\n\n"
        "Required: `category_id` (from `GET /menu/categories`), `package_name`, `price`, "
        "`meal_type` (veg/non-veg/egg), and `food_type`. "
        "Optional: `short_description`, `description`, `discounted_price`, `subscription_price`, "
        "`is_subscription_available`.\n\n"
        "After creation, add items via `POST /menu/items` and images via `POST /menu/images`. "
        "Then make the package available to users with `POST /provider/packages/select`.\n\n"
        "**Flow:** `GET /menu/categories` → `POST /menu/package` → add items → add images → select package"
    )
)
async def create_package(
    request: CreateMenuPackageRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(
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
    response_model=GetMenuPackageResponse,
    summary="Get Package Detail (Provider View)",
    description=(
        "**Fetch full details of a meal package including items and images.**\n\n"
        "Use this on the provider's package management screen to review or edit a package. "
        "Use `package_id` from `GET /menu/list/{provider_id}`."
    )
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
    "/list/{provider_id}",
    summary="List Provider's Packages",
    description=(
        "**Fetch all meal packages created by a specific provider.**\n\n"
        "Pass `is_predefined=true` to fetch only system-wide predefined packages "
        "(templates the provider can adopt). Leave it `false` (default) for the provider's own packages.\n\n"
        "**When to call:** On the provider's 'Manage Packages' screen or when selecting packages to offer."
    )
)
def list_packages(
    provider_id: str,
    is_predefined: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):

    return MenuService.list_provider_packages(
        db,
        provider_id,
        is_predefined=is_predefined,
        current_provider_id=str(current_provider['provider_id'])
    )


@router.put(
    "/update/{package_id}",
    response_model=CommonResponse,
    summary="Update a Meal Package",
    description=(
        "**Edit details of an existing meal package.**\n\n"
        "Only the fields provided will be updated. Changes to price or availability take effect immediately "
        "for new orders (existing subscriptions are not affected).\n\n"
        "**When to call:** On the 'Edit Package' screen. "
        "Use `package_id` from `GET /menu/list/{provider_id}`."
    )
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
    response_model=CommonResponse,
    summary="Delete a Meal Package",
    description=(
        "**Permanently delete a meal package.**\n\n"
        "Cannot delete a package that has active subscriptions linked to it. "
        "Consider marking it as unavailable (`is_available=false`) instead to hide it from users "
        "without affecting existing subscribers.\n\n"
        "**When to call:** On the provider's package management screen."
    )
)
def delete_package(
    package_id: UUID,
    db: Session = Depends(get_db)
):

    return MenuService.delete_package(
        db,
        package_id
    )
