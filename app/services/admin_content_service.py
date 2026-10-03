from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.clock import now_utc
from app.core.errors import DomainError
from app.domain.pricing import validate_package_prices
from app.domain.slots import normalize_plan_slot
from app.models.extra_order_model import ExtraOrder
from app.models.menu_category_model import MenuCategory
from app.models.menu_package_model import MenuPackage
from app.models.provider_model import Provider
from app.models.subscription_plan_model import SubscriptionPlan
from app.models.subscription_model import Subscription
from app.models.serviceable_pincode_model import ServiceablePincode
from app.models.user_address_model import UserAddress
from app.repositories.menu_repository import MenuRepository
from app.services.admin_views import package_admin_view
from app.services.menu_service import active_subscription_count, package_dict


def _package(db: Session, package_id, lock: bool = False) -> MenuPackage:
    q = db.query(MenuPackage).filter(MenuPackage.package_id == package_id)
    if lock:
        q = q.with_for_update()
    pkg = q.first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg


def _open_extra_orders(db: Session, package_id) -> int:
    return db.query(ExtraOrder).filter(
        ExtraOrder.package_reference_id == package_id,
        ExtraOrder.status.in_(("pending", "confirmed", "preparing", "out_for_delivery")),
    ).count()


def _audit_package(db, pkg, before, admin_id, ip, operation="U"):
    record_audit(
        db, table="provider.menu_packages", record_id=pkg.package_id, operation=operation,
        old=before, new=package_admin_view(pkg), actor_id=admin_id, actor_type="admin", ip=ip,
    )


# ── Package Management ────────────────────────────────────

class AdminPackageService:

    @staticmethod
    def create_package(db: Session, payload, admin_id: str, ip: str | None = None):
        category = db.query(MenuCategory).filter(
            MenuCategory.category_id == payload.category_id, MenuCategory.is_active == True  # noqa: E712
        ).first()
        if not category:
            raise DomainError("Invalid category")
        validate_package_prices(payload.price, payload.discounted_price, payload.subscription_price)

        package = MenuRepository.create_package(db, {
            # Catalogue packages belong to Orleeno; provider_id records the creating admin
            "provider_id": admin_id,
            "category_reference_id": payload.category_id,
            "package_name": payload.package_name,
            "short_description": payload.short_description,
            "description": payload.description,
            "meal_type": payload.meal_type,
            "food_type": payload.food_type,
            "price": payload.price,
            "discounted_price": payload.discounted_price,
            "is_subscription_available": payload.is_subscription_available,
            "subscription_price": payload.subscription_price,
            "is_predefined": True,
            "is_active": True,
            "is_available": True,
            "approval_status": "approved",
            "approved_at": now_utc(),
            "approved_by": admin_id,
        })
        for order, item in enumerate(payload.items, start=1):
            MenuRepository.create_package_item(db, {
                "package_reference_id": package.package_id,
                "item_name": item.item_name,
                "quantity": item.quantity,
                "item_order": order,
            })
        _audit_package(db, package, None, admin_id, ip, operation="I")
        db.commit()
        db.refresh(package)
        return {
            "success": True,
            "message": "Orleeno catalogue package created. Kitchens can now offer it.",
            "package": package_admin_view(package),
        }

    @staticmethod
    def list_packages(db: Session, is_predefined: bool = None, is_active: bool = None,
                      is_subscription_available: bool = None, approval_status: str = None,
                      provider_id: str = None, search: str = None, include_deleted: bool = False,
                      page: int = 1, limit: int = 20):
        query = db.query(MenuPackage, Provider.business_name).outerjoin(
            Provider, Provider.provider_id == MenuPackage.provider_id
        )
        if not include_deleted:
            query = query.filter(MenuPackage.deleted_at.is_(None))
        if is_predefined is not None:
            query = query.filter(MenuPackage.is_predefined == is_predefined)
        if is_active is not None:
            query = query.filter(MenuPackage.is_active == is_active)
        if is_subscription_available is not None:
            query = query.filter(MenuPackage.is_subscription_available == is_subscription_available)
        if approval_status:
            query = query.filter(MenuPackage.approval_status == approval_status)
        if provider_id:
            query = query.filter(MenuPackage.provider_id == provider_id)
        if search:
            query = query.filter(MenuPackage.package_name.ilike(f"%{search}%"))

        total = query.count()
        rows = query.order_by(MenuPackage.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {
            "success": True,
            "total": total,
            "page": page,
            "packages": [package_admin_view(pkg, None if pkg.is_predefined else name) for pkg, name in rows],
        }

    @staticmethod
    def get_package(db: Session, package_id: str):
        pkg = _package(db, package_id)
        data = package_dict(pkg)
        data.update(package_admin_view(pkg))
        data["active_subscriptions"] = active_subscription_count(db, pkg.package_id)
        return data

    @staticmethod
    def set_approval(db: Session, package_id: str, *, approve: bool, note: str | None, admin_id: str, ip: str | None = None):
        pkg = _package(db, package_id, lock=True)
        if pkg.deleted_at is not None:
            raise DomainError("This package was deleted")
        before = package_admin_view(pkg)

        if approve:
            if not pkg.items:
                raise DomainError("A package needs at least one item before it can be approved")
            validate_package_prices(pkg.price, pkg.discounted_price, pkg.subscription_price)
            pkg.approval_status = "approved"
            pkg.approval_note = note
            pkg.approved_at = now_utc()
            pkg.approved_by = admin_id
            pkg.is_active = True
        else:
            if not note:
                raise DomainError("Give the kitchen a reason for the rejection")
            pkg.approval_status = "rejected"
            pkg.approval_note = note
            pkg.approved_at = None
            pkg.approved_by = None
            pkg.is_active = False

        _audit_package(db, pkg, before, admin_id, ip)
        db.commit()
        running = active_subscription_count(db, pkg.package_id)
        message = "Package approved and live" if approve else "Package rejected"
        if not approve and running:
            message += f"; {running} running subscription(s) continue at their booked price"
        return {"success": True, "message": message, "package": package_admin_view(pkg)}

    @staticmethod
    def update_package(db: Session, package_id: str, payload, admin_id: str, ip: str | None = None):
        pkg = _package(db, package_id, lock=True)
        if pkg.deleted_at is not None:
            raise DomainError("This package was deleted")
        before = package_admin_view(pkg)
        data = payload.model_dump(exclude_unset=True)

        for key in ("discounted_price", "subscription_price"):
            if key in data and data[key] is not None and data[key] <= 0:
                data[key] = None
        for key in ("package_name", "meal_type", "food_type", "price"):
            if key in data and data[key] is None:
                raise DomainError(f"{key} cannot be empty")

        price = data.get("price", pkg.price)
        discounted = data["discounted_price"] if "discounted_price" in data else pkg.discounted_price
        sub_price = data["subscription_price"] if "subscription_price" in data else pkg.subscription_price
        validate_package_prices(price, discounted, sub_price)
        if data.get("is_active") and pkg.approval_status != "approved":
            raise DomainError("Approve the package to make it live")

        for key, value in data.items():
            setattr(pkg, key, value)

        _audit_package(db, pkg, before, admin_id, ip)
        db.commit()
        db.refresh(pkg)
        running = active_subscription_count(db, pkg.package_id)
        return {
            "success": True,
            "message": "Package updated. Running subscriptions keep the price they were booked at."
            if running else "Package updated",
            "active_subscriptions_unaffected": running,
            "package": package_admin_view(pkg),
        }

    @staticmethod
    def set_subscription_availability(db: Session, package_id: str, payload, admin_id: str, ip: str | None = None):
        pkg = _package(db, package_id, lock=True)
        before = package_admin_view(pkg)
        enable = payload.is_subscription_available

        if payload.subscription_price is not None:
            validate_package_prices(pkg.price, pkg.discounted_price, payload.subscription_price)
            pkg.subscription_price = payload.subscription_price
        # without a subscription price, subscriptions are charged the selling price

        pkg.is_subscription_available = enable
        _audit_package(db, pkg, before, admin_id, ip)
        db.commit()
        db.refresh(pkg)
        return {
            "success": True,
            "message": (
                "Package is now available for subscription" if enable
                else "Package subscription disabled; new subscriptions and switches to it are blocked"
            ),
            "active_subscriptions_unaffected": 0 if enable else active_subscription_count(db, pkg.package_id),
            "package": package_admin_view(pkg),
        }

    @staticmethod
    def delete_package(db: Session, package_id: str, admin_id: str, ip: str | None = None):
        pkg = _package(db, package_id, lock=True)
        if pkg.deleted_at is not None:
            return {"success": True, "message": "Package already deleted"}

        running = active_subscription_count(db, pkg.package_id)
        if running:
            raise DomainError(
                f"Cannot delete: package is in {running} running subscription(s). Deactivate it instead."
            )
        open_orders = _open_extra_orders(db, pkg.package_id)
        if open_orders:
            raise DomainError(f"Cannot delete: {open_orders} one-time order(s) for this package are still open.")

        before = package_admin_view(pkg)
        # Soft delete: past orders, reviews and price snapshots keep their reference
        pkg.deleted_at = now_utc()
        pkg.is_active = False
        pkg.is_available = False
        _audit_package(db, pkg, before, admin_id, ip, operation="D")
        db.commit()
        return {"success": True, "message": "Package deleted"}


# ── Subscription Plan Management ──────────────────────────

def _plan_view(plan: SubscriptionPlan) -> dict:
    return {
        "subscription_plan_id": plan.subscription_plan_id,
        "subscription_type": plan.subscription_type,
        "meal_slot": plan.meal_slot,
        "duration_days": plan.duration_days,
        "is_custom": plan.subscription_type == "custom",
        "free_skips": plan.free_skips,
        "discount_percent": plan.discount_percent,
        "is_active": bool(plan.is_active),
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


class AdminPlanService:

    @staticmethod
    def create_plan(db: Session, payload, admin_id: str, ip: str | None = None):
        try:
            meal_slot = normalize_plan_slot(payload.meal_slot)
        except ValueError as exc:
            raise DomainError(str(exc))

        is_custom = payload.subscription_type == "custom"
        duration = 0 if is_custom else payload.duration_days
        if not is_custom and duration <= 0:
            raise DomainError("duration_days must be greater than 0 (only custom plans have no fixed length)")

        existing = db.query(SubscriptionPlan).filter(
            SubscriptionPlan.subscription_type == payload.subscription_type,
            SubscriptionPlan.meal_slot == meal_slot,
        ).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"A plan for '{payload.subscription_type}' + '{meal_slot}' already exists."
            )

        plan = SubscriptionPlan(
            subscription_type=payload.subscription_type,
            meal_slot=meal_slot,
            duration_days=duration,
            free_skips=payload.free_skips,
            discount_percent=payload.discount_percent,
            is_active=True,
        )
        db.add(plan)
        db.flush()
        record_audit(
            db, table="master.subscription_plans", record_id=plan.subscription_plan_id, operation="I",
            new=_plan_view(plan), actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        db.refresh(plan)
        return {"success": True, "message": "Subscription plan created", "plan": _plan_view(plan)}

    @staticmethod
    def list_plans(db: Session, is_active: bool = None):
        query = db.query(SubscriptionPlan)
        if is_active is not None:
            query = query.filter(SubscriptionPlan.is_active == is_active)
        plans = query.order_by(SubscriptionPlan.subscription_type, SubscriptionPlan.meal_slot).all()
        return {"success": True, "total": len(plans), "plans": [_plan_view(p) for p in plans]}

    @staticmethod
    def get_plan(db: Session, plan_id: str):
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.subscription_plan_id == plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        return _plan_view(plan)

    @staticmethod
    def update_plan(db: Session, plan_id: str, payload, admin_id: str, ip: str | None = None):
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.subscription_plan_id == plan_id).with_for_update().first()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        before = _plan_view(plan)
        update_data = payload.model_dump(exclude_unset=True)

        if plan.subscription_type == "custom":
            update_data.pop("duration_days", None)
        for key in ("free_skips", "discount_percent", "duration_days", "is_active"):
            if key in update_data and update_data[key] is None:
                raise DomainError(f"{key} cannot be empty")

        # Running subscriptions keep the terms they were bought with, so
        # deactivating or editing a plan only affects new purchases.
        for key, value in update_data.items():
            setattr(plan, key, value)
        record_audit(
            db, table="master.subscription_plans", record_id=plan.subscription_plan_id,
            old=before, new=_plan_view(plan), actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        db.refresh(plan)
        running = db.query(Subscription).filter(
            Subscription.plan_reference_id == plan.subscription_plan_id,
            Subscription.status.in_(("active", "paused")),
        ).count()
        return {
            "success": True,
            "message": "Plan updated. Changes apply to new subscriptions only.",
            "active_subscriptions_unaffected": running,
            "plan": _plan_view(plan),
        }


# ── Serviceable Pincodes ──────────────────────────────────

def _pin_view(p: ServiceablePincode) -> dict:
    return {
        "pincode_id": p.pincode_id,
        "pincode": p.pincode,
        "city": p.city,
        "state": p.state,
        "is_active": bool(p.is_active),
        "created_at": p.created_at,
    }


def _pincode_usage(db: Session, pincode: int) -> dict:
    providers = db.query(Provider).filter(Provider.pincode == pincode).count()
    running_subs = (
        db.query(Subscription)
        .join(UserAddress, UserAddress.user_address_id == Subscription.user_address_reference_id)
        .filter(UserAddress.pin_code == str(pincode), Subscription.status.in_(("active", "paused")))
        .count()
    )
    return {"kitchens": providers, "running_subscriptions": running_subs}


class AdminPincodeService:

    @staticmethod
    def list_pincodes(db: Session, is_active: bool = None, city: str = None):
        query = db.query(ServiceablePincode)
        if is_active is not None:
            query = query.filter(ServiceablePincode.is_active == is_active)
        if city:
            query = query.filter(ServiceablePincode.city.ilike(f"%{city}%"))
        pincodes = query.order_by(ServiceablePincode.pincode).all()
        return {"success": True, "total": len(pincodes), "pincodes": [_pin_view(p) for p in pincodes]}

    @staticmethod
    def create_pincode(db: Session, payload, admin_id: str, ip: str | None = None):
        existing = db.query(ServiceablePincode).filter(ServiceablePincode.pincode == payload.pincode).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Pincode {payload.pincode} already exists")
        pincode = ServiceablePincode(pincode=payload.pincode, city=payload.city, state=payload.state, is_active=True)
        db.add(pincode)
        db.flush()
        record_audit(
            db, table="master.serviceable_pincodes", operation="I", new=_pin_view(pincode),
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        db.refresh(pincode)
        return {"success": True, "message": "Pincode added", "pincode": _pin_view(pincode)}

    @staticmethod
    def update_pincode(db: Session, pincode_id: int, payload, admin_id: str, ip: str | None = None):
        pincode = db.query(ServiceablePincode).filter(ServiceablePincode.pincode_id == pincode_id).first()
        if not pincode:
            raise HTTPException(status_code=404, detail="Pincode not found")
        before = _pin_view(pincode)
        update_data = payload.model_dump(exclude_unset=True)
        for key in ("city", "state", "is_active"):
            if key in update_data and update_data[key] is None:
                raise DomainError(f"{key} cannot be empty")
        for key, value in update_data.items():
            setattr(pincode, key, value)
        record_audit(
            db, table="master.serviceable_pincodes", old=before, new=_pin_view(pincode),
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        db.refresh(pincode)
        message = "Pincode updated"
        if before["is_active"] and not pincode.is_active:
            usage = _pincode_usage(db, pincode.pincode)
            message = (
                "Pincode deactivated: no new subscriptions or orders there. "
                f"{usage['running_subscriptions']} running subscription(s) continue."
            )
        return {"success": True, "message": message, "pincode": _pin_view(pincode)}

    @staticmethod
    def delete_pincode(db: Session, pincode_id: int, admin_id: str, ip: str | None = None):
        pincode = db.query(ServiceablePincode).filter(ServiceablePincode.pincode_id == pincode_id).first()
        if not pincode:
            raise HTTPException(status_code=404, detail="Pincode not found")
        usage = _pincode_usage(db, pincode.pincode)
        if usage["kitchens"] or usage["running_subscriptions"]:
            raise DomainError(
                f"Pincode is in use ({usage['kitchens']} kitchen(s), {usage['running_subscriptions']} running "
                "subscription(s)). Deactivate it instead."
            )
        before = _pin_view(pincode)
        db.delete(pincode)
        record_audit(
            db, table="master.serviceable_pincodes", operation="D", old=before,
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return {"success": True, "message": "Pincode deleted"}
