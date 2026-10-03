from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_provider
from app.schemas.package_item_schema import AddPackageItemRequest, UpdatePackageItemRequest
from app.services.package_item_service import PackageItemService

router = APIRouter()


@router.post("/add", summary="Add Item to Package", description="Own packages only.")
def add_package_item(
    request: AddPackageItemRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return PackageItemService.add_package_item(db, current_provider["provider_id"], request)


@router.put("/update/{item_id}", summary="Update Package Item", description="Own packages only.")
def update_package_item(
    item_id: UUID,
    request: UpdatePackageItemRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return PackageItemService.update_package_item(db, current_provider["provider_id"], item_id, request)


@router.delete("/delete/{item_id}", summary="Delete Package Item", description="Own packages only.")
def delete_package_item(
    item_id: UUID,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return PackageItemService.delete_package_item(db, current_provider["provider_id"], item_id)
