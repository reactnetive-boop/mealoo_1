"""Admin: subscription plans (weekly / monthly / custom, discounts, free skips)."""

from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import DomainError
from app.domain.slots import normalize_plan_slot
from app.models.subscription_plan_model import SubscriptionPlan
from app.models.subscription_model import Subscription
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
            raise DomainError(str(exc)) from None

        is_custom = payload.subscription_type == "custom"
        duration = 0 if is_custom else payload.duration_days
        if not is_custom and duration <= 0:
            raise DomainError("duration_days must be greater than 0 (only custom plans have no fixed length)")

        existing = db.query(SubscriptionPlan).filter(
            SubscriptionPlan.subscription_type == payload.subscription_type,
            SubscriptionPlan.meal_slot == meal_slot,
        ).first()
        if existing:
            raise DomainError(f"A plan for '{payload.subscription_type}' + '{meal_slot}' already exists.", 409)

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
            raise DomainError("Plan not found", 404)
        return _plan_view(plan)

    @staticmethod
    def update_plan(db: Session, plan_id: str, payload, admin_id: str, ip: str | None = None):
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.subscription_plan_id == plan_id).with_for_update().first()
        if not plan:
            raise DomainError("Plan not found", 404)
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

