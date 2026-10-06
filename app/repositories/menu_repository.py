from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, selectinload

from app.models.menu_package_model import MenuPackage
from app.models.menu_package_item_model import MenuPackageItem
from app.models.provider_model import Provider
from app.models.provider_selected_package_model import ProviderSelectedPackage
from app.domain.eligibility import provider_sellable_filter, package_sellable_filter, serves_pincode_filter

# Package cards always show items and images: load them in two extra queries
# for the whole list instead of two per package.
WITH_CHILDREN = (selectinload(MenuPackage.items), selectinload(MenuPackage.images))


class MenuRepository:

    @staticmethod
    def create_package(db: Session, package_data: dict):
        package = MenuPackage(**package_data)
        db.add(package)
        db.flush()
        return package

    @staticmethod
    def create_package_item(db: Session, item_data: dict):
        item = MenuPackageItem(**item_data)
        db.add(item)
        return item

    @staticmethod
    def get_package_by_id(db: Session, package_id):
        # Unfiltered lookup; callers apply ownership / visibility rules
        return db.query(MenuPackage).filter(MenuPackage.package_id == package_id).first()

    @staticmethod
    def list_provider_packages(db: Session, provider_id):
        """Own packages (any approval state) plus catalogue packages the kitchen offers."""

        offered = (
            db.query(ProviderSelectedPackage.package_id)
            .filter(
                ProviderSelectedPackage.provider_id == provider_id,
                ProviderSelectedPackage.is_active == True,  # noqa: E712
            )
            .subquery()
        )

        return (
            db.query(MenuPackage)
            .options(*WITH_CHILDREN)
            .filter(
                MenuPackage.deleted_at.is_(None),
                or_(
                    and_(MenuPackage.provider_id == provider_id, MenuPackage.is_predefined == False),  # noqa: E712
                    and_(MenuPackage.is_predefined == True, MenuPackage.package_id.in_(offered)),  # noqa: E712
                ),
            )
            .order_by(MenuPackage.created_at.desc())
            .all()
        )

    @staticmethod
    def list_catalog_packages(db: Session):
        """Live Orleeno catalogue packages a kitchen may offer."""
        return (
            db.query(MenuPackage)
            .options(*WITH_CHILDREN)
            .filter(
                MenuPackage.is_predefined == True,  # noqa: E712
                MenuPackage.approval_status == "approved",
                MenuPackage.is_active == True,  # noqa: E712
                MenuPackage.deleted_at.is_(None),
            )
            .order_by(MenuPackage.created_at.desc())
            .all()
        )

    @staticmethod
    def sellable_offerings(db: Session, pin_code: int):
        """(offering, package, provider) rows customers in `pin_code` may buy."""
        return (
            db.query(ProviderSelectedPackage, MenuPackage, Provider)
            .options(*WITH_CHILDREN)
            .join(MenuPackage, ProviderSelectedPackage.package_id == MenuPackage.package_id)
            .join(Provider, ProviderSelectedPackage.provider_id == Provider.provider_id)
            .filter(
                ProviderSelectedPackage.is_active == True,  # noqa: E712
                package_sellable_filter(),
                provider_sellable_filter(),
                serves_pincode_filter(pin_code),
            )
            .order_by(MenuPackage.created_at.desc())
            .all()
        )
