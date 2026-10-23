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
from app.domain import item_quantity, ratings
from app.domain.pricing import (
    build_quote, current_components, package_price_view, selling_price, subscription_unit_price,
)
from app.domain.slots import expand_plan_slot, package_slots
from app.models.menu_package_model import MenuPackage
from app.models.provider_model import Provider
from app.models.provider_service_area_model import ProviderServiceArea
from app.models.subscription_plan_model import SubscriptionPlan
from app.models.user_address_model import UserAddress
from app.models.user_model import User
from app.repositories.menu_repository import MenuRepository


def kitchen_pincodes(db: Session, providers) -> dict:
    """{provider_id: every pincode the kitchen delivers to} (its own + service areas), one query."""
    providers = list(providers)
    out = {p.provider_id: {p.pincode} - {None} for p in providers}
    if out:
        for pid, pin in (
            db.query(ProviderServiceArea.provider_reference_id, ProviderServiceArea.pincode)
            .filter(ProviderServiceArea.provider_reference_id.in_(list(out)))
        ):
            out.setdefault(pid, set()).add(pin)
    return {pid: sorted(str(x) for x in pins) for pid, pins in out.items()}


def _brief(package: MenuPackage, provider: Provider) -> dict:
    return {
        "package_id": package.package_id,
        "package_name": package.package_name,
        "provider_id": provider.provider_id,
        "provider_name": provider.business_name,
        "primary_image": _primary_image(package),
        "meal_slots": package_slots(package.meal_type),
    }


def _plans(db: Session) -> list:
    return [
        p for p in db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True).all()  # noqa: E712
        if expand_plan_slot(p.meal_slot) and p.subscription_type != "custom" and (p.duration_days or 0) > 0
    ]


def offer_summary(db: Session, offerings) -> dict | None:
    """
    The lowest one-time meal price and the lowest subscription price of what
    a customer can actually buy in this pincode, with the packages they come
    from. None when nothing is on sale (the apps then show no prices or
    offers). All amounts come from the pricing engine.
    """
    offers = [(package, provider) for _, package, provider in offerings if package.is_available]
    if not offers:
        return None
    one_pkg, one_provider = min(offers, key=lambda o: selling_price(o[0]))
    summary = {
        "kitchens": len({str(p.provider_id) for _, p in offers}),
        "packages": len(offers),
        "lowest_one_time_price": selling_price(one_pkg),
        "lowest_one_time_package": _brief(one_pkg, one_provider),
        "lowest_subscription_meal_price": None,
        "lowest_subscription_package": None,
        "subscription_discount_percent": None,
        "starting_plan": None,
    }
    subs = [o for o in offers if o[0].is_subscription_available]
    plans = _plans(db)
    if not subs or not plans:
        return summary
    sub_pkg, sub_provider = min(subs, key=lambda o: subscription_unit_price(o[0]))
    summary["lowest_subscription_meal_price"] = subscription_unit_price(sub_pkg)
    summary["lowest_subscription_package"] = _brief(sub_pkg, sub_provider)
    summary["subscription_discount_percent"] = max(p.discount_percent or 0 for p in plans)

    # the cheapest package's plan for its first meal: monthly when there is one, else the shortest
    served = package_slots(sub_pkg.meal_type)
    single = [p for p in plans if served and expand_plan_slot(p.meal_slot) == served[:1]]
    if single:
        plan = next((p for p in single if p.subscription_type == "monthly"), None) or min(
            single, key=lambda p: p.duration_days
        )
        quote = build_quote(
            current_components(db), kind="subscription", base_unit_price=subscription_unit_price(sub_pkg),
            quantity=1, deliveries=int(plan.duration_days), discount_percent=plan.discount_percent,
        )
        summary["starting_plan"] = {
            "subscription_plan_id": plan.subscription_plan_id,
            "subscription_type": plan.subscription_type,
            "meal_slot": plan.meal_slot,
            "duration_days": plan.duration_days,
            "meals": quote["deliveries"],
            "original_amount": quote["base_amount"],
            "discount_percent": quote["discount_percent"],
            "discount_amount": quote["discount_amount"],
            "final_amount": quote["food_amount"],
            "package": _brief(sub_pkg, sub_provider),
        }
    return summary


def _primary_image(package) -> str | None:
    for img in package.images:
        if img.is_primary:
            return img.image_url
    return package.images[0].image_url if package.images else None


def _offer_view(package: MenuPackage, provider: Provider, kitchen_open_today: bool,
                rating: dict | None = None, pincodes: list | None = None) -> dict:
    return {
        **(rating or ratings.empty()),
        # pincodes this kitchen delivers to: the app checks the address before ordering
        "service_pincodes": pincodes or ([str(provider.pincode)] if provider.pincode else []),
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
            # only when something is on sale here: prices of unavailable kitchens are never shown
            "offer_summary": offer_summary(db, rows) if kitchens else None,
        }

    @staticmethod
    def list_packages(db: Session, pin_code: int):
        pin = parse_pincode(pin_code)
        if pin is None:
            raise DomainError("Enter a valid 6-digit pincode", 422)

        if serviceable_pincode(db, pin) is None:
            return {"success": True, "total": 0, "serviceable": False, "packages": [], "offer_summary": None}

        offerings = MenuRepository.sellable_offerings(db, pin)
        providers = {provider.provider_id: provider for _, _, provider in offerings}
        closed_today = kitchens_on_holiday(db, set(providers), today_local())
        stats = ratings.for_offers(db, ((package.package_id, provider.provider_id) for _, package, provider in offerings))
        pincodes = kitchen_pincodes(db, providers.values())
        result = [
            _offer_view(
                package, provider, provider.provider_id not in closed_today,
                ratings.get(stats, package.package_id, provider.provider_id), pincodes.get(provider.provider_id),
            )
            for _, package, provider in offerings
        ]

        return {
            "success": True,
            "total": len(result),
            "serviceable": True,
            "offer_summary": offer_summary(db, offerings),
            "packages": result,
        }

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

        rating = ratings.get(
            ratings.for_offers(db, [(package.package_id, provider.provider_id)]), package.package_id, provider.provider_id,
        )
        view = _offer_view(
            package, provider, not is_on_holiday(db, provider.provider_id, today_local()),
            rating, kitchen_pincodes(db, [provider]).get(provider.provider_id),
        )
        view["description"] = package.description
        # this package's own reviews (never the kitchen's other packages)
        view["reviews"] = ratings.recent_reviews(db, package.package_id, provider.provider_id, limit=5)
        view["review_total"] = ratings.review_count(db, package.package_id, provider.provider_id)
        view["items"] = [
            {"item_id": i.item_id, "item_name": i.item_name, "item_order": i.item_order or 0, **item_quantity.of(i)}
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
