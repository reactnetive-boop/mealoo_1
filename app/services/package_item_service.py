"""
Items of a kitchen's package. On a live (approved) package the item list is
edited as a pending revision (domain/package_revision.py); the approved list
stays on sale until Orleeno reviews the change.
"""

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.domain import package_revision as revision
from app.models.menu_package_item_model import MenuPackageItem
from app.models.menu_package_model import MenuPackage
from app.repositories.package_item_repository import PackageItemRepository
from app.services.menu_service import owned_package, mark_changed

REVIEW_MESSAGE = " Customers see the current items until the change is approved."


def _locate(db: Session, provider_id: str, item_id):
    """(package, live item or None) for an item id, including items that only exist in a pending revision."""
    item = PackageItemRepository.get_item_by_id(db, item_id)
    if item is not None:
        return owned_package(db, provider_id, item.package_reference_id), item
    pending_owner = (
        db.query(MenuPackage)
        .filter(
            MenuPackage.provider_id == provider_id,
            MenuPackage.pending_changes["items"].contains([{"item_id": str(item_id)}]),
        )
        .first()
    )
    if pending_owner is None:
        raise DomainError("Package item not found", 404)
    return pending_owner, None


class PackageItemService:

    @staticmethod
    def add_package_item(db: Session, provider_id: str, request):
        package = owned_package(db, provider_id, request.package_id)

        if revision.is_live(package):
            items = revision.editable_items(package)
            entry = revision.new_item(request.item_name, request.quantity, request.item_order or len(items) + 1)
            revision.propose_items(package, items + [entry])
            db.commit()
            return {
                "success": True,
                "message": "Item added and sent for review." + REVIEW_MESSAGE,
                "item_id": entry["item_id"],
                "has_pending_changes": True,
            }

        if len(package.items) >= revision.MAX_ITEMS:
            raise DomainError(f"A package can have at most {revision.MAX_ITEMS} items")
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
            "has_pending_changes": False,
        }

    @staticmethod
    def update_package_item(db: Session, provider_id: str, item_id, request):
        package, item = _locate(db, provider_id, item_id)
        updates = {f: getattr(request, f) for f in ("item_name", "quantity", "item_order") if getattr(request, f) is not None}

        if revision.is_live(package):
            items = revision.editable_items(package)
            entry = next((i for i in items if i["item_id"] == str(item_id)), None)
            if entry is None:
                raise DomainError("Package item not found", 404)
            entry.update(updates)
            revision.propose_items(package, items)
            db.commit()
            pending = bool(package.pending_changes)
            return {
                "success": True,
                "message": ("Item change sent for review." + REVIEW_MESSAGE) if pending else "Package item updated successfully",
                "has_pending_changes": pending,
            }

        if item is None:
            raise DomainError("Package item not found", 404)
        changed = False
        for field, value in updates.items():
            if getattr(item, field) != value:
                setattr(item, field, value)
                changed = changed or field != "item_order"
        if changed:
            mark_changed(package)
        db.commit()
        return {"success": True, "message": "Package item updated successfully", "has_pending_changes": False}

    @staticmethod
    def delete_package_item(db: Session, provider_id: str, item_id):
        package, item = _locate(db, provider_id, item_id)

        if revision.is_live(package):
            items = [i for i in revision.editable_items(package) if i["item_id"] != str(item_id)]
            revision.propose_items(package, items)  # refuses an empty list
            db.commit()
            return {
                "success": True,
                "message": "Item removal sent for review." + REVIEW_MESSAGE,
                "has_pending_changes": bool(package.pending_changes),
            }

        if item is None:
            raise DomainError("Package item not found", 404)
        if len(package.items) <= 1:
            raise DomainError("A package must keep at least one item")
        db.delete(item)
        mark_changed(package)
        db.commit()
        return {"success": True, "message": "Package item deleted successfully", "has_pending_changes": False}
