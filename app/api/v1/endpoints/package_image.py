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

@router.post("/upload")
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


@router.delete("/delete/{image_id}")
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


@router.put("/set-primary/{image_id}")
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