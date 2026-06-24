from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.cart_repository import CartRepository
from app.repositories.menu_repository import MenuRepository


def _build_item_dict(item) -> dict:
    pkg = item.package
    price = Decimal(str(pkg.price))
    discounted_price = Decimal(str(pkg.discounted_price)) if pkg.discounted_price else Decimal("0")
    effective_price = price - discounted_price
    return {
        "cart_item_id": item.cart_item_id,
        "package_reference_id": item.package_reference_id,
        "vendor_reference_id": item.vendor_reference_id,
        "quantity": item.quantity,
        "package_name": pkg.package_name,
        "price": price,
        "discounted_price": discounted_price,
        "effective_price": effective_price,
        "item_total": effective_price * item.quantity,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


class CartService:

    @staticmethod
    def add_to_cart(
        db: Session,
        user_id: str,
        payload,
    ):
        package = MenuRepository.get_active_package_by_id(db, payload.package_id)
        if not package:
            raise HTTPException(
                status_code=404,
                detail="Package not found or not available",
            )

        existing = CartRepository.get_by_user_and_package(
            db, user_id, package.package_id
        )

        if existing:
            existing.quantity = payload.quantity
            db.commit()
            db.refresh(existing)
            item = existing
            message = "Cart item quantity updated"
        else:
            data = {
                "user_reference_id": user_id,
                "vendor_reference_id": str(package.provider_id),
                "package_reference_id": str(package.package_id),
                "quantity": payload.quantity,
            }
            item = CartRepository.create(db, data)
            db.commit()
            db.refresh(item)
            message = "Item added to cart"

        return {
            "success": True,
            "message": message,
            "cart_item": _build_item_dict(item),
        }

    @staticmethod
    def get_cart(
        db: Session,
        user_id: str,
    ):
        items = CartRepository.get_all_by_user(db, user_id)

        item_dicts = [_build_item_dict(i) for i in items]

        cart_total = sum(
            Decimal(str(i["item_total"])) for i in item_dicts
        )

        return {
            "success": True,
            "total_items": len(item_dicts),
            "cart_total": cart_total,
            "items": item_dicts,
        }

    @staticmethod
    def update_cart_item(
        db: Session,
        user_id: str,
        cart_item_id: str,
        payload,
    ):
        item = CartRepository.get_by_id(db, cart_item_id)

        if not item:
            raise HTTPException(status_code=404, detail="Cart item not found")

        if str(item.user_reference_id) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        item.quantity = payload.quantity
        db.commit()
        db.refresh(item)

        return {
            "success": True,
            "message": "Cart item updated",
            "cart_item": _build_item_dict(item),
        }

    @staticmethod
    def remove_cart_item(
        db: Session,
        user_id: str,
        cart_item_id: str,
    ):
        item = CartRepository.get_by_id(db, cart_item_id)

        if not item:
            raise HTTPException(status_code=404, detail="Cart item not found")

        if str(item.user_reference_id) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        CartRepository.delete(db, item)
        db.commit()

        return {"success": True, "message": "Item removed from cart"}

    @staticmethod
    def clear_cart(
        db: Session,
        user_id: str,
    ):
        CartRepository.delete_all_by_user(db, user_id)
        db.commit()

        return {"success": True, "message": "Cart cleared"}
