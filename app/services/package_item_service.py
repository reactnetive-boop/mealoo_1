from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.menu_package_item_model import MenuPackageItem
from app.repositories.package_item_repository import PackageItemRepository
from app.services.menu_service import owned_package, mark_changed


def _owned_item(db: Session, provider_id: str, item_id) -> MenuPackageItem:
    item = PackageItemRepository.get_item_by_id(db, item_id)
    if item is None:
        raise DomainError("Package item not found", 404)
    owned_package(db, provider_id, item.package_reference_id)
    return item


class PackageItemService:

    @staticmethod
    def add_package_item(db: Session, provider_id: str, request):
        package = owned_package(db, provider_id, request.package_id)
        if len(package.items) >= 50:
            raise DomainError("A package can have at most 50 items")
        item = MenuPackageItem(
            package_reference_id=package.package_id,
            item_name=request.item_name,
            quantity=request.quantity,
            item_order=request.item_order or len(package.items) + 1,
        )
        db.add(item)
        reapproval = mark_changed(package)
        db.commit()
        db.refresh(item)
        return {
            "success": True,
            "message": "Package item added" + (" and sent for re-approval" if reapproval else ""),
            "item_id": item.item_id,
        }

    @staticmethod
    def update_package_item(db: Session, provider_id: str, item_id, request):
        item = _owned_item(db, provider_id, item_id)
        changed = False
        for field in ("item_name", "quantity", "item_order"):
            value = getattr(request, field)
            if value is not None and getattr(item, field) != value:
                setattr(item, field, value)
                changed = changed or field != "item_order"
        if changed:
            mark_changed(item.menu_package)
        db.commit()
        return {"success": True, "message": "Package item updated successfully"}

    @staticmethod
    def delete_package_item(db: Session, provider_id: str, item_id):
        item = _owned_item(db, provider_id, item_id)
        package = item.menu_package
        if len(package.items) <= 1:
            raise DomainError("A package must keep at least one item")
        db.delete(item)
        mark_changed(package)
        db.commit()
        return {"success": True, "message": "Package item deleted successfully"}
