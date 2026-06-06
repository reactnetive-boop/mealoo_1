from sqlalchemy.orm import Session

from app.models.subscription_plan_model import SubscriptionPlan


class SubscriptionPlanRepository:

    @staticmethod
    def get_all_active(
        db: Session
    ):

        return (
            db.query(SubscriptionPlan)
            .filter(
                SubscriptionPlan.is_active == True
            )
            .order_by(
                SubscriptionPlan.subscription_type
            )
            .all()
        )

    @staticmethod
    def get_by_id(
        db: Session,
        plan_id
    ):

        return (
            db.query(SubscriptionPlan)
            .filter(
                SubscriptionPlan.id == plan_id,
                SubscriptionPlan.is_active == True
            )
            .first()
        )
