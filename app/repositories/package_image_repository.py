from sqlalchemy.orm import Session

from app.models.menu_package_image_model import (
    MenuPackageImage
)


class PackageImageRepository:


    @staticmethod
    def get_image_by_image_id(
        db: Session,
        image_id
    ):

        return db.query(MenuPackageImage).filter(
            MenuPackageImage.image_id == image_id
        ).first()


    @staticmethod
    def delete_package_image(
        db: Session,
        package_image: MenuPackageImage
    ):

        db.delete(package_image)

        db.flush()

        return True