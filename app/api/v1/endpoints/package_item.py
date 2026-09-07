from fastapi import (
    APIRouter,
    Depends
)

from sqlalchemy.orm import Session

from app.core.database import get_db

from app.schemas.package_item_schema import (
    AddPackageItemRequest,
    UpdatePackageItemRequest
)

from app.services.package_item_service import (
    PackageItemService
)

router = APIRouter()


@router.post(
    "/add",
    summary="Add Item to Package",
    description=(
        "**Add a food item to a meal package's item list.**\n\n"
        "Requires `package_id`, `item_name`, and `item_order` (display position). "
        "Optional: `quantity` (e.g. '2 pieces', '1 bowl'). "
        "Items are shown to users on the package detail screen.\n\n"
        "**When to call:** After `POST /menu/package` to define what is included in the meal. "
        "Add all items before making the package available to users."
    )
)
async def add_package_item(
    request: AddPackageItemRequest,
    db: Session = Depends(get_db)
):

    return PackageItemService.add_package_item(
        db,
        request
    )


@router.put(
    "/update/{item_id}",
    summary="Update Package Item",
    description=(
        "**Edit the name, quantity, or display order of an existing package item.**\n\n"
        "Use `item_id` from `GET /menu/get/{package_id}`. "
        "Changes are reflected immediately in the user-facing package detail view."
    )
)
async def update_package_item(
    item_id: str,
    request: UpdatePackageItemRequest,
    db: Session = Depends(get_db)
):

    return PackageItemService.update_package_item(
        db,
        item_id,
        request
    )


@router.delete(
    "/delete/{item_id}",
    summary="Delete Package Item",
    description=(
        "**Remove a food item from a meal package.**\n\n"
        "Use `item_id` from `GET /menu/get/{package_id}`. "
        "Existing subscriptions are not affected; the item simply stops appearing in the package listing."
    )
)
async def delete_package_item(
    item_id: str,
    db: Session = Depends(get_db)
):

    return PackageItemService.delete_package_item(
        db,
        item_id
    )
