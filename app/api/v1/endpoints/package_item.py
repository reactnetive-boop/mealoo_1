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

@router.post("/add")
async def add_package_item(
    request: AddPackageItemRequest,
    db: Session = Depends(get_db)
):

    return PackageItemService.add_package_item(
        db,
        request
    )


@router.put("/update/{item_id}")
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


@router.delete("/delete/{item_id}")
async def delete_package_item(
    item_id: str,
    db: Session = Depends(get_db)
):

    return PackageItemService.delete_package_item(
        db,
        item_id
    )