from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.menu_package_model import MenuPackage
from app.models.subscription_plan_model import SubscriptionPlan
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.serviceable_pincode_model import ServiceablePincode
from app.repositories.menu_repository import MenuRepository


# ── Package Management ────────────────────────────────────

class AdminPackageService:

    @staticmethod
    def create_package(db: Session, payload, admin_id: str):
        package_data = {
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
        }
        package = MenuRepository.create_package(db, package_data)

        for item in payload.items:
            MenuRepository.create_package_item(db, {
                "package_reference_id": package.package_id,
                "item_name": item.item_name,
                "quantity": item.quantity,
            })

        db.commit()
        db.refresh(package)
        return {"success": True, "message": "Predefined package created", "package": package}

    @staticmethod
    def list_packages(db: Session, is_predefined: bool = None, is_active: bool = None,
                      is_subscription_available: bool = None,
                      provider_id: str = None, search: str = None, page: int = 1, limit: int = 20):
        query = db.query(MenuPackage)
        if is_predefined is not None:
            query = query.filter(MenuPackage.is_predefined == is_predefined)
        if is_active is not None:
            query = query.filter(MenuPackage.is_active == is_active)
        if is_subscription_available is not None:
            query = query.filter(MenuPackage.is_subscription_available == is_subscription_available)
        if provider_id:
            query = query.filter(MenuPackage.provider_id == provider_id)
        if search:
            query = query.filter(MenuPackage.package_name.ilike(f"%{search}%"))

        total = query.count()
        packages = query.order_by(MenuPackage.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page, "packages": packages}

    @staticmethod
    def get_package(db: Session, package_id: str):
        pkg = db.query(MenuPackage).filter(MenuPackage.package_id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")
        return pkg

    @staticmethod
    def update_package(db: Session, package_id: str, payload):
        pkg = db.query(MenuPackage).filter(MenuPackage.package_id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")

        update_data = payload.model_dump(exclude_unset=True)

        if "is_active" in update_data and not update_data["is_active"]:
            in_use = db.query(SubscriptionPackage).join(
                Subscription, SubscriptionPackage.subscription_reference_id == Subscription.subscription_id
            ).filter(
                SubscriptionPackage.package_reference_id == package_id,
                Subscription.status == "active"
            ).count()
            if in_use:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot deactivate: package is in {in_use} active subscription(s)."
                )

        for key, value in update_data.items():
            setattr(pkg, key, value)
        db.commit()
        db.refresh(pkg)

        return {"success": True, "message": "Package updated", "package": pkg}

    @staticmethod
    def set_subscription_availability(db: Session, package_id: str, payload):
        pkg = db.query(MenuPackage).filter(MenuPackage.package_id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")

        enable = payload.is_subscription_available

        if payload.subscription_price is not None:
            pkg.subscription_price = payload.subscription_price

        # a package cannot be opened for subscription without a price to charge
        if enable and (pkg.subscription_price is None or pkg.subscription_price <= 0):
            raise HTTPException(
                status_code=400,
                detail="subscription_price is required (and must be > 0) to enable subscription for this package"
            )

        pkg.is_subscription_available = enable

        # disabling only blocks NEW subscriptions / switches; running ones keep going
        active_count = 0
        if not enable:
            active_count = db.query(SubscriptionPackage).join(
                Subscription, SubscriptionPackage.subscription_reference_id == Subscription.subscription_id
            ).filter(
                SubscriptionPackage.package_reference_id == package_id,
                Subscription.status == "active"
            ).count()

        db.commit()
        db.refresh(pkg)

        message = (
            "Package is now available for subscription" if enable
            else "Package subscription disabled; new subscriptions and switches to it are blocked"
        )
        return {
            "success": True,
            "message": message,
            "active_subscriptions_unaffected": active_count,
            "package": pkg,
        }

    @staticmethod
    def delete_package(db: Session, package_id: str):
        pkg = db.query(MenuPackage).filter(MenuPackage.package_id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")

        in_use = db.query(SubscriptionPackage).join(
            Subscription, SubscriptionPackage.subscription_reference_id == Subscription.subscription_id
        ).filter(
            SubscriptionPackage.package_reference_id == package_id,
            Subscription.status == "active"
        ).count()
        if in_use:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete: package is in {in_use} active subscription(s). Deactivate it instead."
            )

        db.delete(pkg)
        db.commit()
        return {"success": True, "message": "Package deleted"}


# ── Subscription Plan Management ──────────────────────────

class AdminPlanService:

    @staticmethod
    def create_plan(db: Session, payload):
        existing = db.query(SubscriptionPlan).filter(
            SubscriptionPlan.subscription_type == payload.subscription_type,
            SubscriptionPlan.meal_slot == payload.meal_slot
        ).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"A plan for '{payload.subscription_type}' + '{payload.meal_slot}' already exists."
            )

        plan = SubscriptionPlan(
            subscription_type=payload.subscription_type,
            meal_slot=payload.meal_slot,
            duration_days=payload.duration_days,
            free_skips=payload.free_skips,
            discount_percent=payload.discount_percent,
            is_active=True,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        return {"success": True, "message": "Subscription plan created", "plan": plan}

    @staticmethod
    def list_plans(db: Session, is_active: bool = None):
        query = db.query(SubscriptionPlan)
        if is_active is not None:
            query = query.filter(SubscriptionPlan.is_active == is_active)
        plans = query.order_by(SubscriptionPlan.subscription_type, SubscriptionPlan.meal_slot).all()
        return {"success": True, "total": len(plans), "plans": plans}

    @staticmethod
    def get_plan(db: Session, plan_id: str):
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.subscription_plan_id == plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        return plan

    @staticmethod
    def update_plan(db: Session, plan_id: str, payload):
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.subscription_plan_id == plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        update_data = payload.model_dump(exclude_unset=True)

        if "is_active" in update_data and not update_data["is_active"]:
            in_use = db.query(Subscription).filter(
                Subscription.plan_reference_id == plan_id,
                Subscription.status == "active"
            ).count()
            if in_use:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot deactivate: plan is used in {in_use} active subscription(s)."
                )

        for key, value in update_data.items():
            setattr(plan, key, value)
        db.commit()
        db.refresh(plan)

        return {"success": True, "message": "Plan updated", "plan": plan}


# ── Serviceable Pincodes ──────────────────────────────────

class AdminPincodeService:

    @staticmethod
    def list_pincodes(db: Session, is_active: bool = None, city: str = None):
        query = db.query(ServiceablePincode)
        if is_active is not None:
            query = query.filter(ServiceablePincode.is_active == is_active)
        if city:
            query = query.filter(ServiceablePincode.city.ilike(f"%{city}%"))
        pincodes = query.order_by(ServiceablePincode.pincode).all()
        return {"success": True, "total": len(pincodes), "pincodes": pincodes}

    @staticmethod
    def create_pincode(db: Session, payload):
        existing = db.query(ServiceablePincode).filter(
            ServiceablePincode.pincode == payload.pincode
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Pincode {payload.pincode} already exists")

        pincode = ServiceablePincode(
            pincode=payload.pincode,
            city=payload.city,
            state=payload.state,
            is_active=True
        )
        db.add(pincode)
        db.commit()
        db.refresh(pincode)

        return {"success": True, "message": "Pincode added", "pincode": pincode}

    @staticmethod
    def update_pincode(db: Session, pincode_id: int, payload):
        pincode = db.query(ServiceablePincode).filter(
            ServiceablePincode.pincode_id == pincode_id
        ).first()
        if not pincode:
            raise HTTPException(status_code=404, detail="Pincode not found")

        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(pincode, key, value)
        db.commit()
        db.refresh(pincode)

        return {"success": True, "message": "Pincode updated", "pincode": pincode}

    @staticmethod
    def delete_pincode(db: Session, pincode_id: int):
        pincode = db.query(ServiceablePincode).filter(
            ServiceablePincode.pincode_id == pincode_id
        ).first()
        if not pincode:
            raise HTTPException(status_code=404, detail="Pincode not found")

        db.delete(pincode)
        db.commit()
        return {"success": True, "message": "Pincode deleted"}
