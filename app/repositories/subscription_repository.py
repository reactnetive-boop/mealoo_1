from sqlalchemy.orm import Session

from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage


class SubscriptionRepository:

    @staticmethod
    def get_active_by_user(
        db: Session,
        user_id
    ):

        return (
            db.query(Subscription)
            .filter(
                Subscription.user_id == user_id,
                Subscription.status == "active"
            )
            .first()
        )

    @staticmethod
    def get_all_by_user(
        db: Session,
        user_id
    ):

        return (
            db.query(Subscription)
            .filter(
                Subscription.user_id == user_id
            )
            .order_by(
                Subscription.created_at.desc()
            )
            .all()
        )

    @staticmethod
    def get_by_id(
        db: Session,
        subscription_id
    ):

        return (
            db.query(Subscription)
            .filter(
                Subscription.id == subscription_id
            )
            .first()
        )

    @staticmethod
    def create(
        db: Session,
        subscription_data: dict
    ):

        subscription = Subscription(**subscription_data)

        db.add(subscription)

        db.flush()

        return subscription

    @staticmethod
    def create_package(
        db: Session,
        package_data: dict
    ):

        sub_package = SubscriptionPackage(**package_data)

        db.add(sub_package)

        db.flush()

        return sub_package

    @staticmethod
    def cancel(
        db: Session,
        subscription: Subscription,
        cancel_reason: str
    ):

        from datetime import datetime, timezone

        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.now(timezone.utc)
        subscription.cancel_reason = cancel_reason

        db.flush()

        return subscription
