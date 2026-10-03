from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.menu_package_image_model import MenuPackageImage
from app.repositories.package_image_repository import PackageImageRepository
from app.services.menu_service import owned_package
from app.utils.file_helper import save_package_image, delete_upload

MAX_IMAGES = 10


def _owned_image(db: Session, provider_id: str, image_id) -> MenuPackageImage:
    image = PackageImageRepository.get_image_by_image_id(db, image_id)
    if image is None:
        raise DomainError("Image not found", 404)
    owned_package(db, provider_id, image.package_reference_id)
    return image


class PackageImageService:

    @staticmethod
    def upload_package_image(db: Session, provider_id: str, package_id, file: UploadFile):
        package = owned_package(db, provider_id, package_id)
        if len(package.images) >= MAX_IMAGES:
            raise DomainError(f"A package can have at most {MAX_IMAGES} photos")

        path = save_package_image(file)
        image = MenuPackageImage(
            package_reference_id=package.package_id,
            image_url=path,
            is_primary=len(package.images) == 0,
            display_order=len(package.images) + 1,
        )
        db.add(image)
        db.commit()
        db.refresh(image)
        return {
            "success": True,
            "message": "Package image uploaded successfully",
            "image_id": image.image_id,
            "image_url": image.image_url,
        }

    @staticmethod
    def delete_package_image(db: Session, provider_id: str, image_id):
        image = _owned_image(db, provider_id, image_id)
        was_primary = image.is_primary
        package_id = image.package_reference_id
        path = image.image_url
        db.delete(image)
        db.flush()
        if was_primary:
            # Promote the next photo so the package keeps a cover image
            nxt = (
                db.query(MenuPackageImage)
                .filter(MenuPackageImage.package_reference_id == package_id)
                .order_by(MenuPackageImage.display_order.asc())
                .first()
            )
            if nxt:
                nxt.is_primary = True
        db.commit()
        delete_upload(path)
        return {"success": True, "message": "Package image deleted successfully"}

    @staticmethod
    def set_primary_image(db: Session, provider_id: str, image_id):
        image = _owned_image(db, provider_id, image_id)
        db.query(MenuPackageImage).filter(
            MenuPackageImage.package_reference_id == image.package_reference_id
        ).update({"is_primary": False}, synchronize_session=False)
        image.is_primary = True
        db.commit()
        return {"success": True, "message": "Primary image updated successfully"}
