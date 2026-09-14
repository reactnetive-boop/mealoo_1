from datetime import date as date_type, timedelta

from sqlalchemy.orm import Session

from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.user_address_model import UserAddress
from app.models.provider_model import Provider
from app.models.delivery_boy_model import DeliveryBoy


class SubscriptionRepository:

    @staticmethod
    def get_active_by_user(
        db: Session,
        user_id
    ):

        return (
            db.query(Subscription)
            .filter(
                Subscription.user_reference_id == user_id,
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
                Subscription.user_reference_id == user_id
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
                Subscription.subscription_id == subscription_id
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
    def get_subscribed_packages_by_user(
        db: Session,
        user_id
    ):
        return (
            db.query(SubscriptionPackage, MenuPackage, Subscription)
            .join(
                Subscription,
                SubscriptionPackage.subscription_reference_id == Subscription.subscription_id
            )
            .join(
                MenuPackage,
                SubscriptionPackage.package_reference_id == MenuPackage.package_id
            )
            .filter(
                Subscription.user_reference_id == user_id
            )
            .order_by(Subscription.created_at.desc())
            .all()
        )

    @staticmethod
    def get_all_by_vendor(
        db: Session,
        vendor_id,
        status: str = None
    ):
        query = (
            db.query(Subscription)
            .filter(Subscription.vendor_reference_id == vendor_id)
        )
        if status:
            query = query.filter(Subscription.status == status)
        return query.order_by(Subscription.created_at.desc()).all()

    @staticmethod
    def get_by_id_and_vendor(
        db: Session,
        subscription_id,
        vendor_id
    ):
        return (
            db.query(Subscription)
            .filter(
                Subscription.subscription_id == subscription_id,
                Subscription.vendor_reference_id == vendor_id
            )
            .first()
        )

    @staticmethod
    def get_orders_by_vendor(
        db: Session,
        vendor_id,
        order_date: date_type = None,
        status: str = None
    ):
        query = (
            db.query(Order)
            .filter(Order.vendor_reference_id == vendor_id)
        )
        if order_date:
            query = query.filter(Order.order_date == order_date)
        if status:
            query = query.filter(Order.status == status)
        return query.order_by(Order.order_date.asc(), Order.meal_slot.asc()).all()

    @staticmethod
    def get_order_by_id_and_vendor(
        db: Session,
        order_id,
        vendor_id
    ):
        return (
            db.query(Order)
            .filter(
                Order.order_id == order_id,
                Order.vendor_reference_id == vendor_id
            )
            .first()
        )

    @staticmethod
    def get_orders_by_subscription(
        db: Session,
        subscription_id,
        status: str = None,
        order_date: date_type = None
    ):
        query = (
            db.query(Order)
            .filter(Order.subscription_reference_id == subscription_id)
        )
        if status:
            query = query.filter(Order.status == status)
        if order_date:
            query = query.filter(Order.order_date == order_date)
        return query.order_by(Order.order_date.asc(), Order.meal_slot.asc()).all()

    @staticmethod
    def get_order_detail_by_id_and_subscription(
        db: Session,
        order_id,
        subscription_id
    ):
        # Provider and delivery boy are outer-joined: a missing kitchen row or
        # an unassigned order shouldn't 404 the customer's view.
        return (
            db.query(Order, UserAddress, Provider, DeliveryBoy)
            .join(UserAddress, Order.delivery_address_reference_id == UserAddress.user_address_id)
            .outerjoin(Provider, Order.vendor_reference_id == Provider.provider_id)
            .outerjoin(DeliveryBoy, Order.delivery_boy_reference_id == DeliveryBoy.delivery_boy_id)
            .filter(
                Order.order_id == order_id,
                Order.subscription_reference_id == subscription_id
            )
            .first()
        )

    @staticmethod
    def get_order_by_id_and_subscription(
        db: Session,
        order_id,
        subscription_id
    ):
        return (
            db.query(Order)
            .filter(
                Order.order_id == order_id,
                Order.subscription_reference_id == subscription_id
            )
            .first()
        )

    @staticmethod
    def skip_order(
        db: Session,
        order: Order,
        is_free_skip: bool,
        skip_requested_at,
        skip_deadline
    ) -> Order:

        order.status = "skipped"
        order.is_free_skip = is_free_skip
        order.skip_requested_at = skip_requested_at
        order.skip_deadline = skip_deadline

        db.flush()

        return order

    @staticmethod
    def consume_free_skip(
        db: Session,
        subscription: Subscription
    ) -> Subscription:

        subscription.free_skips_used = (subscription.free_skips_used or 0) + 1

        db.flush()

        return subscription

    @staticmethod
    def get_packages_with_menu_by_subscription(
        db: Session,
        subscription_id
    ):
        return (
            db.query(SubscriptionPackage, MenuPackage)
            .join(MenuPackage, SubscriptionPackage.package_reference_id == MenuPackage.package_id)
            .filter(SubscriptionPackage.subscription_reference_id == subscription_id)
            .all()
        )

    @staticmethod
    def pause(
        db: Session,
        subscription: Subscription,
        pause_start_date: date_type
    ) -> Subscription:

        subscription.status = "paused"
        subscription.pause_start_date = pause_start_date

        db.flush()

        return subscription

    @staticmethod
    def resume(
        db: Session,
        subscription: Subscription,
        days_paused: int,
        new_end_date: date_type
    ) -> Subscription:

        subscription.status = "active"
        subscription.end_date = new_end_date
        subscription.total_days_paused = (subscription.total_days_paused or 0) + days_paused
        subscription.pause_start_date = None

        db.flush()

        return subscription

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
