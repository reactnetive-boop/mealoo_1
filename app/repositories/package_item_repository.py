from sqlalchemy.orm import Session

from app.models.menu_package_item_model import (
    MenuPackageItem
)


class PackageItemRepository:

    @staticmethod
    def create_package_item(
        db: Session,
        package_item: MenuPackageItem
    ):

        db.add(package_item)

        db.flush()

        db.refresh(package_item)

        return package_item


    @staticmethod
    def get_item_by_id(
        db: Session,
        item_id
    ):

        return db.query(MenuPackageItem).filter(
            MenuPackageItem.item_id == item_id
        ).first()


    @staticmethod
    def delete_package_item(
        db: Session,
        package_item: MenuPackageItem
    ):

        db.delete(package_item)

        db.flush()

        return True