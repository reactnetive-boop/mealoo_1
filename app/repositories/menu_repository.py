from sqlalchemy import or_
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

from app.models.menu_package_image_model import MenuPackageImage

from app.models.provider_model import Provider

from app.models.provider_selected_package_model import ProviderSelectedPackage

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
    
    @staticmethod
    def list_provider_packages(
        db,
        provider_id
    ):

        selected_package_ids = (
            db.query(ProviderSelectedPackage.package_id)
            .filter(
                ProviderSelectedPackage.provider_id == provider_id,
                ProviderSelectedPackage.is_active == True
            )
            .subquery()
        )

        return (
            db.query(MenuPackage)
            .filter(
                MenuPackage.is_active == True,
                or_(
                    MenuPackage.provider_id == provider_id,
                    MenuPackage.package_id.in_(selected_package_ids)
                )
            )
            .order_by(MenuPackage.created_at.desc())
            .all()
        )

    @staticmethod
    def list_predefined_packages_not_selected(
        db,
        admin_id,
        current_provider_id
    ):
        already_selected = (
            db.query(ProviderSelectedPackage.package_id)
            .filter(
                ProviderSelectedPackage.provider_id == current_provider_id,
                ProviderSelectedPackage.is_active == True
            )
            .subquery()
        )

        return (
            db.query(MenuPackage)
            .filter(
                MenuPackage.provider_id == admin_id,
                MenuPackage.is_predefined == True,
                MenuPackage.is_active == True,
                MenuPackage.package_id.notin_(already_selected)
            )
            .order_by(MenuPackage.created_at.desc())
            .all()
        )
    
    @staticmethod
    def update_package(
        db,
        package,
        update_data
    ):

        for key, value in update_data.items():

            setattr(package, key, value)

        db.commit()

        db.refresh(package)

        return package
    
    @staticmethod
    def delete_package(
        db,
        package
    ):

        package.is_active = False

        db.commit()

        return True

    @staticmethod
    def get_packages_by_pincode(
        db: Session,
        pin_code: int
    ):
        return (
            db.query(ProviderSelectedPackage, MenuPackage)
            .join(
                MenuPackage,
                ProviderSelectedPackage.package_id == MenuPackage.package_id
            )
            .join(
                Provider,
                ProviderSelectedPackage.provider_id == Provider.provider_id
            )
            .filter(
                MenuPackage.is_available == True,
                MenuPackage.is_active == True,
                ProviderSelectedPackage.is_active == True,
                Provider.pincode == pin_code
            )
            .order_by(MenuPackage.created_at.desc())
            .all()
        )

    @staticmethod
    def get_active_package_by_id(
        db: Session,
        package_id
    ):

        return (
            db.query(MenuPackage)
            .filter(
                MenuPackage.package_id == package_id,
                MenuPackage.is_available == True,
                MenuPackage.is_active == True
            )
            .first()
        )

    @staticmethod
    def get_subscribable_packages_by_pincode(
        db: Session,
        pin_code: int
    ):

        return (
            db.query(MenuPackage)
            .join(
                Provider,
                MenuPackage.provider_id == Provider.provider_id
            )
            .filter(
                MenuPackage.is_subscription_available == True,
                MenuPackage.is_available == True,
                MenuPackage.is_active == True,
                Provider.pincode == pin_code
            )
            .order_by(
                MenuPackage.created_at.desc()
            )
            .all()
        )