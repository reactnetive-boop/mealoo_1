from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.domain.eligibility import assert_sellable
from app.domain.pricing import package_price_view, money
from app.models.menu_package_model import MenuPackage
from app.repositories.cart_repository import CartRepository


def _build_item_dict(item) -> dict:
    pkg = item.package
    prices = package_price_view(pkg)
    return {
        "cart_item_id": item.cart_item_id,
        "package_reference_id": item.package_reference_id,
        "vendor_reference_id": item.vendor_reference_id,
        "quantity": item.quantity,
        "package_name": pkg.package_name,
        "price": prices["base_price"],
        # Selling price for one-time orders (not a discount amount)
        "discounted_price": prices["selling_price"],
        "effective_price": prices["selling_price"],
        "subscription_unit_price": prices["subscription_unit_price"],
        "item_total": money(prices["selling_price"] * item.quantity),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _owned(db: Session, user_id: str, cart_item_id):
    item = CartRepository.get_by_id(db, cart_item_id)
    if not item or str(item.user_reference_id) != user_id:
        raise DomainError("Cart item not found", 404)
    return item


class CartService:

    @staticmethod
    def add_to_cart(db: Session, user_id: str, payload):
        package = db.query(MenuPackage).filter(MenuPackage.package_id == payload.package_id).first()
        if package is None:
            raise DomainError("Package not found or not available", 404)
        provider_id = payload.provider_id or (None if package.is_predefined else package.provider_id)
        if provider_id is None:
            raise DomainError("provider_id is required for Orleeno catalogue packages", 422)

        provider, package = assert_sellable(db, provider_id=provider_id, package_id=package.package_id)

        existing = CartRepository.get_by_user_and_package(db, user_id, package.package_id)
        if existing:
            existing.quantity = payload.quantity
            existing.vendor_reference_id = provider.provider_id
            item = existing
            message = "Cart item quantity updated"
        else:
            item = CartRepository.create(db, {
                "user_reference_id": user_id,
                "vendor_reference_id": str(provider.provider_id),
                "package_reference_id": str(package.package_id),
                "quantity": payload.quantity,
            })
            message = "Item added to cart"
        db.commit()
        db.refresh(item)
        return {"success": True, "message": message, "cart_item": _build_item_dict(item)}

    @staticmethod
    def get_cart(db: Session, user_id: str):
        items = CartRepository.get_all_by_user(db, user_id)
        item_dicts = [_build_item_dict(i) for i in items]
        return {
            "success": True,
            "total_items": len(item_dicts),
            "cart_total": sum((i["item_total"] for i in item_dicts), money(0)),
            "items": item_dicts,
        }

    @staticmethod
    def update_cart_item(db: Session, user_id: str, cart_item_id: str, payload):
        item = _owned(db, user_id, cart_item_id)
        item.quantity = payload.quantity
        db.commit()
        db.refresh(item)
        return {"success": True, "message": "Cart item updated", "cart_item": _build_item_dict(item)}

    @staticmethod
    def remove_cart_item(db: Session, user_id: str, cart_item_id: str):
        item = _owned(db, user_id, cart_item_id)
        CartRepository.delete(db, item)
        db.commit()
        return {"success": True, "message": "Item removed from cart"}

    @staticmethod
    def clear_cart(db: Session, user_id: str):
        CartRepository.delete_all_by_user(db, user_id)
        db.commit()
        return {"success": True, "message": "Cart cleared"}
