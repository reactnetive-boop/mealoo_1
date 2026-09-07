from sqlalchemy.orm import Session

from app.models.menu_package_image_model import (
    MenuPackageImage
)


class PackageImageRepository:

    @staticmethod
    def create_package_image(
        db: Session,
        package_image: MenuPackageImage
    ):

        db.add(package_image)

        db.commit()

        db.refresh(package_image)

        return package_image


    @staticmethod
    def get_image_by_image_id(
        db: Session,
        image_id
    ):

        return db.query(MenuPackageImage).filter(
            MenuPackageImage.image_id == image_id
        ).first()


    @staticmethod
    def remove_primary_images(
        db: Session,
        package_id
    ):

        db.query(MenuPackageImage).filter(
            MenuPackageImage.package_reference_id == package_id
        ).update({
            "is_primary": False
        })

        db.commit()


    @staticmethod
    def delete_package_image(
        db: Session,
        package_image: MenuPackageImage
    ):

        db.delete(package_image)

        db.commit()

        return True