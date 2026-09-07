from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File
)

from sqlalchemy.orm import Session

from app.core.database import get_db

from app.services.package_image_service import (
    PackageImageService
)

router = APIRouter()


@router.post(
    "/upload",
    summary="Upload Package Image",
    description=(
        "**Upload a photo for a meal package.**\n\n"
        "Pass `package_id` as a query parameter and the image file as `multipart/form-data`. "
        "Multiple images can be uploaded per package. "
        "The first image uploaded automatically becomes the primary image.\n\n"
        "**When to call:** After creating a package with `POST /menu/package`. "
        "Use `PUT /menu/images/set-primary/{image_id}` to change which image is shown first in listings."
    )
)
async def upload_package_image(
    package_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    return await (
        PackageImageService.upload_package_image(
            db,
            package_id,
            file
        )
    )


@router.delete(
    "/delete/{image_id}",
    summary="Delete Package Image",
    description=(
        "**Remove a specific image from a meal package.**\n\n"
        "Use `image_id` returned from the upload or from `GET /menu/get/{package_id}`. "
        "If the deleted image was the primary image, set another image as primary with "
        "`PUT /menu/images/set-primary/{image_id}`."
    )
)
async def delete_package_image(
    image_id: UUID,
    db: Session = Depends(get_db)
):

    return (
        PackageImageService.delete_package_image(
            db,
            image_id
        )
    )


@router.put(
    "/set-primary/{image_id}",
    summary="Set Primary Package Image",
    description=(
        "**Set a specific image as the primary/cover image for a package.**\n\n"
        "The primary image is the one displayed on package cards in the user-facing listing. "
        "Only one image can be primary at a time — setting a new one automatically unsets the previous.\n\n"
        "Use `image_id` from `GET /menu/get/{package_id}`."
    )
)
async def set_primary_image(
    image_id: UUID,
    db: Session = Depends(get_db)
):

    return (
        PackageImageService.set_primary_image(
            db,
            image_id
        )
    )
