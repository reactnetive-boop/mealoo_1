import os

from fastapi import (
    HTTPException,
    UploadFile
)

from app.models.menu_package_image_model import (
    MenuPackageImage
)

from app.repositories.menu_repository import (
    MenuRepository
)

from app.repositories.package_image_repository import (
    PackageImageRepository
)

from app.utils.file_helper import (
    save_package_image
)


class PackageImageService:

    @staticmethod
    async def upload_package_image(
        db,
        package_id,
        file: UploadFile
    ):

        package = (
            MenuRepository.get_package_by_id(
                db,
                package_id
            )
        )

        if not package:

            raise HTTPException(
                status_code=404,
                detail="Package not found"
            )

        allowed_extensions = [
            ".jpg",
            ".jpeg",
            ".png",
            ".webp"
        ]

        file_extension = os.path.splitext(
            file.filename
        )[1].lower()

        if file_extension not in allowed_extensions:

            raise HTTPException(
                status_code=400,
                detail="Invalid image format"
            )

        file_path = save_package_image(
            file
        )

        is_primary = (
            len(package.images) == 0
        )

        package_image = MenuPackageImage(
            package_reference_id=package_id,
            image_url=file_path,
            is_primary=is_primary
        )

        package_image = (
            PackageImageRepository.create_package_image(
                db,
                package_image
            )
        )

        return {
            "success": True,
            "message": "Package image uploaded successfully",
            "image_id": package_image.image_id,
            "image_url": package_image.image_url
        }


    @staticmethod
    def delete_package_image(
        db,
        image_id
    ):

        package_image = (
            PackageImageRepository.get_image_by_image_id(
                db,
                image_id
            )
        )

        if not package_image:

            raise HTTPException(
                status_code=404,
                detail="Image not found"
            )

        if os.path.exists(
            package_image.image_url
        ):

            os.remove(
                package_image.image_url
            )

        PackageImageRepository.delete_package_image(
            db,
            package_image
        )

        return {
            "success": True,
            "message": "Package image deleted successfully"
        }


    @staticmethod
    def set_primary_image(
        db,
        image_id
    ):

        package_image = (
            PackageImageRepository.get_image_by_image_id(
                db,
                image_id
            )
        )

        if not package_image:

            raise HTTPException(
                status_code=404,
                detail="Image not found"
            )

        PackageImageRepository.remove_primary_images(
            db,
            package_image.image_id
        )

        package_image.is_primary = True

        db.commit()

        db.refresh(package_image)

        return {
            "success": True,
            "message": "Primary image updated successfully"
        }