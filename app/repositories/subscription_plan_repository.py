from sqlalchemy import distinct
from sqlalchemy.orm import Session

from app.models.subscription_plan_model import SubscriptionPlan


class SubscriptionPlanRepository:

    @staticmethod
    def get_all_active(
        db: Session,
        meal_slot: str = None,
        subscription_type: str = None
    ):

        query = (
            db.query(SubscriptionPlan)
            .filter(SubscriptionPlan.is_active == True)
        )

        if meal_slot:
            query = query.filter(
                SubscriptionPlan.meal_slot == meal_slot
            )

        if subscription_type:
            query = query.filter(
                SubscriptionPlan.subscription_type == subscription_type
            )

        return (
            query
            .order_by(
                SubscriptionPlan.subscription_type,
                SubscriptionPlan.meal_slot
            )
            .all()
        )

    @staticmethod
    def get_distinct_meal_slots(db: Session):
        rows = (
            db.query(distinct(SubscriptionPlan.meal_slot))
            .filter(SubscriptionPlan.is_active == True)
            .order_by(SubscriptionPlan.meal_slot)
            .all()
        )
        return [r[0] for r in rows]

    @staticmethod
    def get_distinct_subscription_types(db: Session):
        rows = (
            db.query(distinct(SubscriptionPlan.subscription_type))
            .filter(SubscriptionPlan.is_active == True)
            .order_by(SubscriptionPlan.subscription_type)
            .all()
        )
        return [r[0] for r in rows]

    @staticmethod
    def get_by_id(
        db: Session,
        plan_id
    ):

        return (
            db.query(SubscriptionPlan)
            .filter(
                SubscriptionPlan.subscription_plan_id == plan_id,
                SubscriptionPlan.is_active == True
            )
            .first()
        )
