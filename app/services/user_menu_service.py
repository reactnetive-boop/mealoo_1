from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.core.errors import DomainError
from app.domain.eligibility import (
    serviceable_pincode,
    parse_pincode,
    provider_block_reason,
    package_block_reason,
    offering,
    is_on_holiday,
    kitchens_on_holiday,
)
from app.domain.pricing import package_price_view
from app.domain.slots import package_slots
from app.models.menu_package_model import MenuPackage
from app.models.provider_model import Provider
from app.models.user_address_model import UserAddress
from app.models.user_model import User
from app.repositories.menu_repository import MenuRepository


def _primary_image(package) -> str | None:
    for img in package.images:
        if img.is_primary:
            return img.image_url
    return package.images[0].image_url if package.images else None


def _offer_view(package: MenuPackage, provider: Provider, kitchen_open_today: bool) -> dict:
    return {
        "package_id": package.package_id,
        "category_reference_id": package.category_reference_id,
        "provider_id": provider.provider_id,
        "provider_name": provider.business_name,
        "provider_area": provider.area,
        "is_predefined": bool(package.is_predefined),
        "package_name": package.package_name,
        "short_description": package.short_description,
        "meal_type": package.meal_type,
        "meal_slots": package_slots(package.meal_type),
        "food_type": package.food_type,
        "food_types": [t for t in (package.food_type or "").split(",") if t],
        "price": package.price,
        "discounted_price": package.discounted_price,
        "is_subscription_available": bool(package.is_subscription_available),
        "subscription_price": package.subscription_price,
        "is_available": bool(package.is_available),
        "kitchen_open_today": kitchen_open_today,
        "primary_image": _primary_image(package),
        **package_price_view(package),
    }


class UserMenuService:

    @staticmethod
    def serviceability(db: Session, pin_code) -> dict:
        pin = parse_pincode(pin_code)
        if pin is None:
            raise DomainError("Enter a valid 6-digit pincode", 422)

        if serviceable_pincode(db, pin) is None:
            return {
                "success": True,
                "pin_code": pin,
                "serviceable": False,
                "status": "pincode_not_serviceable",
                "message": f"Orleeno does not deliver to {pin} yet.",
                "kitchens": 0,
                "packages": 0,
            }

        rows = MenuRepository.sellable_offerings(db, pin)
        kitchens = len({str(r[2].provider_id) for r in rows})
        return {
            "success": True,
            "pin_code": pin,
            "serviceable": kitchens > 0,
            "status": "ok" if kitchens else "no_kitchens",
            "message": None if kitchens else f"No kitchens are serving {pin} right now. Please check back soon.",
            "kitchens": kitchens,
            "packages": len(rows),
        }

    @staticmethod
    def list_packages(db: Session, pin_code: int):
        pin = parse_pincode(pin_code)
        if pin is None:
            raise DomainError("Enter a valid 6-digit pincode", 422)

        if serviceable_pincode(db, pin) is None:
            return {"success": True, "total": 0, "serviceable": False, "packages": []}

        offerings = MenuRepository.sellable_offerings(db, pin)
        closed_today = kitchens_on_holiday(db, {provider.provider_id for _, _, provider in offerings}, today_local())
        result = [
            _offer_view(package, provider, provider.provider_id not in closed_today)
            for _, package, provider in offerings
        ]

        return {"success": True, "total": len(result), "serviceable": True, "packages": result}

    @staticmethod
    def get_package(db: Session, package_id, provider_id=None):
        package = db.query(MenuPackage).filter(MenuPackage.package_id == package_id).first()
        if package_block_reason(package):
            raise DomainError("Package not found or unavailable", 404)

        if provider_id is None:
            if package.is_predefined:
                raise DomainError("provider_id is required for Orleeno catalogue packages", 422)
            provider_id = package.provider_id

        provider = db.query(Provider).filter(Provider.provider_id == provider_id).first()
        if provider_block_reason(provider) or offering(db, provider_id, package.package_id) is None:
            raise DomainError("Package not found or unavailable", 404)

        view = _offer_view(package, provider, not is_on_holiday(db, provider.provider_id, today_local()))
        view["description"] = package.description
        view["items"] = [
            {"item_id": i.item_id, "item_name": i.item_name, "quantity": i.quantity, "item_order": i.item_order or 0}
            for i in sorted(package.items, key=lambda i: i.item_order or 0)
        ]
        view["images"] = [
            {"image_id": i.image_id, "image_url": i.image_url, "is_primary": bool(i.is_primary), "display_order": i.display_order or 0}
            for i in package.images
        ]
        return view

    @staticmethod
    def customer_state(db: Session, user_id: str) -> dict:
        """What the customer app should show first; computed from server data only."""

        user = db.query(User).filter(User.user_id == user_id).first()
        addresses = (
            db.query(UserAddress)
            .filter(UserAddress.user_reference_id == user_id, UserAddress.is_active == True)  # noqa: E712
            .order_by(UserAddress.is_default.desc(), UserAddress.created_at.desc())
            .all()
        )
        default = next((a for a in addresses if a.is_default), addresses[0] if addresses else None)

        service = None
        if default is not None and parse_pincode(default.pin_code) is not None:
            service = UserMenuService.serviceability(db, default.pin_code)

        if user.status != "active":
            next_step = "account_inactive"
        elif default is None:
            next_step = "add_address"
        elif not service or service["status"] == "pincode_not_serviceable":
            next_step = "area_not_serviceable"
        elif service["status"] == "no_kitchens":
            next_step = "no_kitchens"
        else:
            next_step = "browse"

        return {
            "success": True,
            "user_id": str(user.user_id),
            "is_authenticated": True,
            "is_mobile_verified": bool(user.phone_verified),
            "is_active": user.status == "active",
            "status": user.status,
            "is_profile_completed": bool(user.is_profile_completed),
            "has_default_address": default is not None,
            "default_address_id": str(default.user_address_id) if default else None,
            "default_pincode": default.pin_code if default else None,
            "is_serviceable": bool(service and service["serviceable"]),
            "serviceability_status": service["status"] if service else None,
            "next_step": next_step,
        }
