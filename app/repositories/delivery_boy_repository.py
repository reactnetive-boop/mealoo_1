from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.delivery_boy_model import DeliveryBoy
from app.models.delivery_boy_otp_log_model import DeliveryBoyOTPLog
from app.models.delivery_boy_document_model import DeliveryBoyDocument
from app.models.delivery_boy_payout_model import DeliveryBoyPayoutDetails
from app.models.delivery_boy_notification_model import DeliveryBoyNotification
from app.models.order_model import Order
from app.models.extra_order_model import ExtraOrder
from app.models.user_model import User
from app.models.user_address_model import UserAddress
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.menu_package_model import MenuPackage
from app.models.provider_model import Provider


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
        db.flush()
        db.refresh(obj)
        return obj

    @staticmethod
    def update(db: Session, delivery_boy: DeliveryBoy, data: dict) -> DeliveryBoy:
        for key, value in data.items():
            setattr(delivery_boy, key, value)
        db.flush()
        db.refresh(delivery_boy)
        return delivery_boy

    # ── OTP ───────────────────────────────────────────────

    @staticmethod
    def create_otp(db: Session, data: dict) -> DeliveryBoyOTPLog:
        otp_log = DeliveryBoyOTPLog(**data)
        db.add(otp_log)
        db.flush()
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
    def get_subscription_order_detail(db: Session, order_id, delivery_boy_id):
        # Provider is outer-joined: a missing kitchen row shouldn't 404 the order.
        return (
            db.query(Order, User, UserAddress, Subscription, Provider)
            .join(User, Order.user_reference_id == User.user_id)
            .join(UserAddress, Order.delivery_address_reference_id == UserAddress.user_address_id)
            .join(Subscription, Order.subscription_reference_id == Subscription.subscription_id)
            .outerjoin(Provider, Order.vendor_reference_id == Provider.provider_id)
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
    def get_extra_order_detail(db: Session, order_id, delivery_boy_id):
        return (
            db.query(ExtraOrder, User, UserAddress, MenuPackage, Provider)
            .join(User, ExtraOrder.user_reference_id == User.user_id)
            .join(UserAddress, ExtraOrder.address_reference_id == UserAddress.user_address_id)
            .join(MenuPackage, ExtraOrder.package_reference_id == MenuPackage.package_id)
            .outerjoin(Provider, ExtraOrder.vendor_reference_id == Provider.provider_id)
            .filter(
                ExtraOrder.extra_order_id == order_id,
                ExtraOrder.delivery_boy_reference_id == delivery_boy_id
            )
            .first()
        )

    # ── Documents ─────────────────────────────────────────

    @staticmethod
    def list_documents(db: Session, delivery_boy_id):
        return (
            db.query(DeliveryBoyDocument)
            .filter(DeliveryBoyDocument.delivery_boy_reference_id == delivery_boy_id)
            .order_by(DeliveryBoyDocument.document_type.asc())
            .all()
        )

    @staticmethod
    def get_document_by_type(db: Session, delivery_boy_id, document_type: str):
        return (
            db.query(DeliveryBoyDocument)
            .filter(
                DeliveryBoyDocument.delivery_boy_reference_id == delivery_boy_id,
                DeliveryBoyDocument.document_type == document_type
            )
            .first()
        )

    @staticmethod
    def upsert_document(db: Session, delivery_boy_id, document_type: str, file_url: str):
        doc = DeliveryBoyRepository.get_document_by_type(db, delivery_boy_id, document_type)
        if doc:
            doc.file_url = file_url
            doc.status = "pending"  # re-uploads go back to review
        else:
            doc = DeliveryBoyDocument(
                delivery_boy_reference_id=delivery_boy_id,
                document_type=document_type,
                file_url=file_url,
            )
            db.add(doc)
        db.flush()
        db.refresh(doc)
        return doc

    # ── Payout details ────────────────────────────────────

    @staticmethod
    def get_payout_details(db: Session, delivery_boy_id):
        return (
            db.query(DeliveryBoyPayoutDetails)
            .filter(DeliveryBoyPayoutDetails.delivery_boy_reference_id == delivery_boy_id)
            .first()
        )

    @staticmethod
    def upsert_payout_details(db: Session, delivery_boy_id, data: dict):
        payout = DeliveryBoyRepository.get_payout_details(db, delivery_boy_id)
        if payout:
            for key, value in data.items():
                setattr(payout, key, value)
        else:
            payout = DeliveryBoyPayoutDetails(
                delivery_boy_reference_id=delivery_boy_id,
                **data
            )
            db.add(payout)
        db.flush()
        db.refresh(payout)
        return payout

    # ── Notifications ─────────────────────────────────────

    @staticmethod
    def create_notification(
        db: Session,
        delivery_boy_id,
        type: str,
        title: str,
        body: str,
        data: dict = None,
        commit: bool = True
    ):
        notification = DeliveryBoyNotification(
            delivery_boy_reference_id=delivery_boy_id,
            type=type,
            title=title,
            body=body,
            data=data,
        )
        db.add(notification)
        if commit:
            db.flush()
            db.refresh(notification)
        else:
            db.flush()
        return notification

    @staticmethod
    def list_notifications(db: Session, delivery_boy_id, limit: int = 50):
        return (
            db.query(DeliveryBoyNotification)
            .filter(DeliveryBoyNotification.delivery_boy_reference_id == delivery_boy_id)
            .order_by(DeliveryBoyNotification.created_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def count_unread_notifications(db: Session, delivery_boy_id) -> int:
        return (
            db.query(DeliveryBoyNotification)
            .filter(
                DeliveryBoyNotification.delivery_boy_reference_id == delivery_boy_id,
                DeliveryBoyNotification.is_read == False
            )
            .count()
        )

    @staticmethod
    def get_notification_by_id(db: Session, delivery_boy_id, notification_id):
        return (
            db.query(DeliveryBoyNotification)
            .filter(
                DeliveryBoyNotification.delivery_boy_notification_id == notification_id,
                DeliveryBoyNotification.delivery_boy_reference_id == delivery_boy_id
            )
            .first()
        )

    @staticmethod
    def mark_notification_read(db: Session, notification: DeliveryBoyNotification):
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        db.flush()
        db.refresh(notification)
        return notification

    @staticmethod
    def mark_all_notifications_read(db: Session, delivery_boy_id) -> int:
        updated = (
            db.query(DeliveryBoyNotification)
            .filter(
                DeliveryBoyNotification.delivery_boy_reference_id == delivery_boy_id,
                DeliveryBoyNotification.is_read == False
            )
            .update({
                DeliveryBoyNotification.is_read: True,
                DeliveryBoyNotification.read_at: datetime.now(timezone.utc)
            })
        )
        db.flush()
        return updated
