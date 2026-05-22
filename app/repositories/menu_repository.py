from sqlalchemy.orm import Session

from app.models.menu_category_model import (
    MenuCategory
)

from app.models.menu_package_model import (
    MenuPackage
)

from app.models.menu_package_item_model import (
    MenuPackageItem
)


class MenuRepository:

    @staticmethod
    def create_package(
        db: Session,
        package_data: dict
    ):

        package = MenuPackage(
            **package_data
        )

        db.add(package)

        db.flush()

        return package

    @staticmethod
    def create_package_item(
        db: Session,
        item_data: dict
    ):

        item = MenuPackageItem(
            **item_data
        )

        db.add(item)

        return item

    @staticmethod
    def get_packages_by_provider(
        db: Session,
        provider_id: str
    ):

        return (
            db.query(MenuPackage)
            .filter(
                MenuPackage.provider_id
                == provider_id,

                MenuPackage.is_active == True
            )
            .all()
        )

    @staticmethod
    def get_package_by_id(
        db: Session,
        package_id: str
    ):

        return (
            db.query(MenuPackage)
            .filter(
                MenuPackage.package_id
                == package_id,

                MenuPackage.is_active == True
            )
            .first()
        )