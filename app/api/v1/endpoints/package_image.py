from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_provider
from app.services.package_image_service import PackageImageService

router = APIRouter()


@router.post(
    "/upload",
    summary="Upload Package Image",
    description="Own packages only. JPEG, PNG or WEBP up to 5 MB (`multipart/form-data`, field `file`).",
)
def upload_package_image(
    package_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return PackageImageService.upload_package_image(db, current_provider["provider_id"], package_id, file)


@router.delete("/delete/{image_id}", summary="Delete Package Image", description="Own packages only.")
def delete_package_image(
    image_id: UUID,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return PackageImageService.delete_package_image(db, current_provider["provider_id"], image_id)


@router.put("/set-primary/{image_id}", summary="Set Primary Package Image", description="Own packages only.")
def set_primary_image(
    image_id: UUID,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return PackageImageService.set_primary_image(db, current_provider["provider_id"], image_id)
