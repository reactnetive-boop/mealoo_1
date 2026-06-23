from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.delivery_boy_model import DeliveryBoy
from app.models.delivery_boy_otp_log_model import DeliveryBoyOTPLog
from app.models.order_model import Order
from app.models.extra_order_model import ExtraOrder
from app.models.user_model import User
from app.models.user_address_model import UserAddress
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.menu_package_model import MenuPackage


class DeliveryBoyRepository:

    # ── Profile ───────────────────────────────────────────

    @staticmethod
    def get_by_mobile(db: Session, mobile_number: str) -> Optional[DeliveryBoy]:
        return (
            db.query(DeliveryBoy)
            .filter(DeliveryBoy.mobile_number == mobile_number)
            .first()
        )

    @staticmethod
    def get_by_id(db: Session, delivery_boy_id) -> Optional[DeliveryBoy]:
        return (
            db.query(DeliveryBoy)
            .filter(DeliveryBoy.delivery_boy_id == delivery_boy_id)
            .first()
        )

    @staticmethod
    def create(db: Session, data: dict) -> DeliveryBoy:
        obj = DeliveryBoy(**data)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def update(db: Session, delivery_boy: DeliveryBoy, data: dict) -> DeliveryBoy:
        for key, value in data.items():
            setattr(delivery_boy, key, value)
        db.commit()
        db.refresh(delivery_boy)
        return delivery_boy

    # ── OTP ───────────────────────────────────────────────

    @staticmethod
    def create_otp(db: Session, data: dict) -> DeliveryBoyOTPLog:
        otp_log = DeliveryBoyOTPLog(**data)
        db.add(otp_log)
        db.commit()
        db.refresh(otp_log)
        return otp_log

    @staticmethod
    def get_latest_otp(db: Session, mobile_number: str) -> Optional[DeliveryBoyOTPLog]:
        return (
            db.query(DeliveryBoyOTPLog)
            .filter(
                DeliveryBoyOTPLog.mobile_number == mobile_number,
                DeliveryBoyOTPLog.is_verified == False
            )
            .order_by(DeliveryBoyOTPLog.created_at.desc())
            .first()
        )

    # ── Subscription Orders ───────────────────────────────

    @staticmethod
    def get_subscription_orders(
        db: Session,
        delivery_boy_id,
        order_date: date = None,
        meal_slot: str = None,
        status: str = None
    ):
        query = db.query(Order).filter(Order.delivery_boy_reference_id == delivery_boy_id)
        if order_date:
            query = query.filter(Order.order_date == order_date)
        if meal_slot:
            query = query.filter(Order.meal_slot == meal_slot)
        if status:
            query = query.filter(Order.status == status)
        return query.order_by(Order.order_date.asc(), Order.meal_slot.asc()).all()

    @staticmethod
    def get_subscription_order_detail(db: Session, order_id, delivery_boy_id):
        return (
            db.query(Order, User, UserAddress, Subscription)
            .join(User, Order.user_reference_id == User.user_id)
            .join(UserAddress, Order.delivery_address_reference_id == UserAddress.user_address_id)
            .join(Subscription, Order.subscription_reference_id == Subscription.subscription_id)
            .filter(
                Order.order_id == order_id,
                Order.delivery_boy_reference_id == delivery_boy_id
            )
            .first()
        )

    @staticmethod
    def get_subscription_order_by_id(db: Session, order_id, delivery_boy_id):
        return (
            db.query(Order)
            .filter(
                Order.order_id == order_id,
                Order.delivery_boy_reference_id == delivery_boy_id
            )
            .first()
        )

    @staticmethod
    def get_subscription_packages_for_order(db: Session, subscription_id):
        return (
            db.query(SubscriptionPackage, MenuPackage)
            .join(MenuPackage, SubscriptionPackage.package_reference_id == MenuPackage.package_id)
            .filter(SubscriptionPackage.subscription_reference_id == subscription_id)
            .all()
        )

    # ── Extra Orders ──────────────────────────────────────

    @staticmethod
    def get_extra_orders(
        db: Session,
        delivery_boy_id,
        delivery_date: date = None,
        meal_slot: str = None,
        status: str = None
    ):
        query = db.query(ExtraOrder).filter(ExtraOrder.delivery_boy_reference_id == delivery_boy_id)
        if delivery_date:
            query = query.filter(ExtraOrder.delivery_date == delivery_date)
        if meal_slot:
            query = query.filter(ExtraOrder.meal_slot == meal_slot)
        if status:
            query = query.filter(ExtraOrder.status == status)
        return query.order_by(ExtraOrder.delivery_date.asc(), ExtraOrder.meal_slot.asc()).all()

    @staticmethod
    def get_extra_order_detail(db: Session, order_id, delivery_boy_id):
        return (
            db.query(ExtraOrder, User, UserAddress, MenuPackage)
            .join(User, ExtraOrder.user_reference_id == User.user_id)
            .join(UserAddress, ExtraOrder.address_reference_id == UserAddress.user_address_id)
            .join(MenuPackage, ExtraOrder.package_reference_id == MenuPackage.package_id)
            .filter(
                ExtraOrder.extra_order_id == order_id,
                ExtraOrder.delivery_boy_reference_id == delivery_boy_id
            )
            .first()
        )

    @staticmethod
    def get_extra_order_by_id(db: Session, order_id, delivery_boy_id):
        return (
            db.query(ExtraOrder)
            .filter(
                ExtraOrder.extra_order_id == order_id,
                ExtraOrder.delivery_boy_reference_id == delivery_boy_id
            )
            .first()
        )
