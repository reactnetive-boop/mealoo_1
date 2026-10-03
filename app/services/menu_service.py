"""
Kitchen-side package management.

Ownership: a kitchen can only change packages it created. Orleeno catalogue
packages (is_predefined, created by an admin) are read-only for kitchens;
they can only offer them (select) and set their own daily capacity.

Approval: new packages start 'pending'. Any change to what a customer buys
(name, description, meal times, food type, prices, items) sends an approved
package back to 'pending' until an admin re-approves it. Existing
subscriptions keep their frozen price either way.
"""

from sqlalchemy.orm import Session

from app.core.clock import now_utc, today_local
from app.core.errors import DomainError
from app.domain import capacity
from app.domain.pricing import validate_package_prices, package_price_view
from app.models.menu_category_model import MenuCategory
from app.models.menu_package_model import MenuPackage
from app.models.provider_selected_package_model import ProviderSelectedPackage
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.repositories.menu_repository import MenuRepository
from app.repositories.provider_selected_package_repository import ProviderSelectedPackageRepository

MATERIAL_FIELDS = {
    "package_name",
    "short_description",
    "description",
    "meal_type",
    "food_type",
    "price",
    "discounted_price",
    "subscription_price",
    "is_subscription_available",
}


def _not_found():
    return DomainError("Package not found", 404)


def owned_package(db: Session, provider_id: str, package_id) -> MenuPackage:
    """A package this kitchen created, not deleted. 404 otherwise (no ID probing)."""
    package = MenuRepository.get_package_by_id(db, package_id)
    if (
        package is None
        or package.deleted_at is not None
        or package.is_predefined
        or str(package.provider_id) != str(provider_id)
    ):
        raise _not_found()
    return package


def visible_package(db: Session, provider_id: str, package_id) -> MenuPackage:
    """Own package, or a live catalogue package, or one this kitchen offers."""
    package = MenuRepository.get_package_by_id(db, package_id)
    if package is None or package.deleted_at is not None:
        raise _not_found()
    if str(package.provider_id) == str(provider_id) and not package.is_predefined:
        return package
    if package.is_predefined and package.approval_status == "approved" and package.is_active:
        return package
    if ProviderSelectedPackageRepository.get_provider_package(db, provider_id, package.package_id):
        return package
    raise _not_found()


def mark_changed(package: MenuPackage) -> bool:
    """Send an approved package back for review. Returns True if it changed state."""
    if package.approval_status == "approved":
        package.approval_status = "pending"
        package.approval_note = "Changed by kitchen - waiting for re-approval"
        return True
    if package.approval_status == "rejected":
        package.approval_status = "pending"
        return True
    return False


def active_subscription_count(db: Session, package_id, provider_id=None) -> int:
    q = (
        db.query(SubscriptionPackage)
        .join(Subscription, SubscriptionPackage.subscription_reference_id == Subscription.subscription_id)
        .filter(
            SubscriptionPackage.package_reference_id == package_id,
            Subscription.status.in_(("active", "paused")),
        )
    )
    if provider_id is not None:
        q = q.filter(Subscription.vendor_reference_id == provider_id)
    return q.count()


def package_dict(package: MenuPackage, *, daily_capacity=None, is_offered=None) -> dict:
    data = {
        "package_id": package.package_id,
        "provider_id": package.provider_id,
        "category_reference_id": package.category_reference_id,
        "package_name": package.package_name,
        "short_description": package.short_description,
        "description": package.description,
        "meal_type": package.meal_type,
        "food_type": package.food_type,
        "price": package.price,
        "discounted_price": package.discounted_price,
        "is_subscription_available": bool(package.is_subscription_available),
        "subscription_price": package.subscription_price,
        "is_available": bool(package.is_available),
        "is_active": bool(package.is_active),
        "is_predefined": bool(package.is_predefined),
        "approval_status": package.approval_status,
        "approval_note": package.approval_note,
        "daily_capacity": daily_capacity,
        "is_offered": is_offered,
        "image_url": next((i.image_url for i in package.images if i.is_primary), None)
        or (package.images[0].image_url if package.images else None),
        "items": [
            {"item_id": i.item_id, "item_name": i.item_name, "quantity": i.quantity, "item_order": i.item_order}
            for i in sorted(package.items, key=lambda i: i.item_order or 0)
        ],
        "images": [
            {"image_id": i.image_id, "image_url": i.image_url, "is_primary": bool(i.is_primary)}
            for i in package.images
        ],
        "created_at": package.created_at,
    }
    data.update(package_price_view(package))
    return data


class MenuService:

    @staticmethod
    def create_package(db: Session, provider_id: str, request):

        category = (
            db.query(MenuCategory)
            .filter(MenuCategory.category_id == request.category_id, MenuCategory.is_active == True)  # noqa: E712
            .first()
        )
        if not category:
            raise DomainError("Invalid category")

        validate_package_prices(request.price, request.discounted_price, request.subscription_price)

        package = MenuRepository.create_package(db, {
            "provider_id": provider_id,
            "category_reference_id": str(request.category_id),
            "package_name": request.package_name,
            "short_description": request.short_description,
            "description": request.description,
            "meal_type": request.meal_type,
            "food_type": request.food_type,
            "price": request.price,
            "discounted_price": request.discounted_price,
            "is_subscription_available": request.is_subscription_available,
            "subscription_price": request.subscription_price,
            # Kitchens cannot self-publish: an admin approves the package
            "is_active": False,
            "is_available": True,
            "is_predefined": False,
            "approval_status": "pending",
        })

        db.add(ProviderSelectedPackage(
            provider_id=provider_id,
            package_id=package.package_id,
            daily_capacity=request.daily_capacity,
        ))

        for order, item in enumerate(request.items, start=1):
            MenuRepository.create_package_item(db, {
                "package_reference_id": package.package_id,
                "item_name": item.item_name,
                "quantity": item.quantity,
                "item_order": order,
            })

        db.commit()

        return {
            "success": True,
            "message": "Package created and sent for approval",
            "package_id": str(package.package_id),
            "approval_status": package.approval_status,
        }

    @staticmethod
    def get_package_details(db: Session, provider_id: str, package_id):
        package = visible_package(db, provider_id, package_id)
        selection = ProviderSelectedPackageRepository.get_provider_package(db, provider_id, package.package_id)
        return package_dict(
            package,
            daily_capacity=selection.daily_capacity if selection else None,
            is_offered=selection is not None,
        )

    @staticmethod
    def list_provider_packages(db: Session, provider_id: str):
        capacities = ProviderSelectedPackageRepository.get_capacities_for_provider(db, provider_id)
        packages = MenuRepository.list_provider_packages(db, provider_id)
        return [
            package_dict(
                p,
                daily_capacity=capacities.get(str(p.package_id)),
                is_offered=str(p.package_id) in capacities,
            )
            for p in packages
        ]

    @staticmethod
    def list_catalog(db: Session, provider_id: str):
        selected = ProviderSelectedPackageRepository.get_capacities_for_provider(db, provider_id)
        packages = MenuRepository.list_catalog_packages(db)
        return [
            package_dict(p, daily_capacity=selected.get(str(p.package_id)), is_offered=str(p.package_id) in selected)
            for p in packages
        ]

    @staticmethod
    def update_package(db: Session, provider_id: str, package_id, request):
        package = owned_package(db, provider_id, package_id)
        update_data = request.model_dump(exclude_unset=True)

        # Explicit allow-list: kitchens can never set approval / activation
        update_data = {k: v for k, v in update_data.items() if k in MATERIAL_FIELDS | {"is_available"}}

        validate_package_prices(
            update_data.get("price", package.price),
            update_data.get("discounted_price", package.discounted_price),
            update_data.get("subscription_price", package.subscription_price),
        )

        material = any(
            k in MATERIAL_FIELDS and getattr(package, k) != v for k, v in update_data.items()
        )
        for key, value in update_data.items():
            setattr(package, key, value)

        reapproval = mark_changed(package) if material else False
        db.commit()

        return {
            "success": True,
            "message": (
                "Package updated and sent for re-approval" if reapproval else "Package updated successfully"
            ),
            "approval_status": package.approval_status,
        }

    @staticmethod
    def delete_package(db: Session, provider_id: str, package_id):
        package = owned_package(db, provider_id, package_id)
        in_use = active_subscription_count(db, package.package_id)
        if in_use:
            raise DomainError(
                f"This package has {in_use} running subscription(s). Mark it unavailable instead; "
                "it can be deleted once they end."
            )
        package.deleted_at = now_utc()
        package.is_active = False
        db.query(ProviderSelectedPackage).filter(
            ProviderSelectedPackage.package_id == package.package_id
        ).update({"is_active": False}, synchronize_session=False)
        db.commit()
        return {"success": True, "message": "Package deleted successfully"}

    # ── Catalogue offering + capacity ─────────────────────────

    @staticmethod
    def select_catalog_package(db: Session, provider_id: str, package_id, daily_capacity=None):
        package = MenuRepository.get_package_by_id(db, package_id)
        if (
            package is None
            or package.deleted_at is not None
            or not package.is_predefined
            or package.approval_status != "approved"
            or not package.is_active
        ):
            raise DomainError("This catalogue package is not available", 404)

        if ProviderSelectedPackageRepository.get_provider_package(db, provider_id, package.package_id):
            raise DomainError("You already offer this package", 409)

        previous = (
            db.query(ProviderSelectedPackage)
            .filter(ProviderSelectedPackage.provider_id == provider_id, ProviderSelectedPackage.package_id == package.package_id)
            .first()
        )
        if previous:
            previous.is_active = True
            previous.daily_capacity = daily_capacity
        else:
            db.add(ProviderSelectedPackage(provider_id=provider_id, package_id=package.package_id, daily_capacity=daily_capacity))
        db.commit()
        return {"success": True, "message": "Package added to your menu", "daily_capacity": daily_capacity}

    @staticmethod
    def unselect_catalog_package(db: Session, provider_id: str, package_id):
        selection = ProviderSelectedPackageRepository.get_provider_package(db, provider_id, package_id)
        package = MenuRepository.get_package_by_id(db, package_id)
        if selection is None or package is None or not package.is_predefined:
            raise DomainError("Package not found in your menu", 404)
        in_use = active_subscription_count(db, package_id, provider_id)
        if in_use:
            raise DomainError(f"{in_use} running subscription(s) use this package from your kitchen")
        selection.is_active = False
        db.commit()
        return {"success": True, "message": "Package removed from your menu"}

    @staticmethod
    def get_capacity(db: Session, provider_id: str, package_id):
        selection = ProviderSelectedPackageRepository.get_provider_package(db, provider_id, package_id)
        if not selection:
            raise DomainError("You do not offer this package", 404)
        return {
            "success": True,
            "message": "Capacity fetched successfully",
            "daily_capacity": selection.daily_capacity,
            "current_peak_demand": capacity.peak_future_demand(db, provider_id, today_local(), package_id),
        }

    @staticmethod
    def set_capacity(db: Session, provider_id: str, package_id, new_capacity):
        selection = ProviderSelectedPackageRepository.get_provider_package(db, provider_id, package_id)
        if not selection:
            raise DomainError("You do not offer this package", 404)
        peak = capacity.peak_future_demand(db, provider_id, today_local(), package_id)
        if new_capacity is not None and new_capacity < peak:
            raise DomainError(
                f"Cannot set capacity to {new_capacity}: {peak} are already booked for a single "
                f"meal on an upcoming day. Capacity must be at least {peak}."
            )
        selection.daily_capacity = new_capacity
        db.commit()
        return {
            "success": True,
            "message": f"Capacity updated to {new_capacity}" if new_capacity is not None else "Capacity limit removed",
            "daily_capacity": selection.daily_capacity,
            "current_peak_demand": peak,
        }
