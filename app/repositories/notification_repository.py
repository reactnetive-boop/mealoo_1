from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.notification_model import Notification


class NotificationRepository:

    @staticmethod
    def create(db: Session, data: dict) -> Notification:
        notification = Notification(**data)
        db.add(notification)
        db.commit()
        db.refresh(notification)
        return notification

    @staticmethod
    def get_by_id_and_user(db: Session, notification_id, user_id) -> Notification:
        return (
            db.query(Notification)
            .filter(
                Notification.notification_id == notification_id,
                Notification.user_reference_id == user_id
            )
            .first()
        )

    @staticmethod
    def get_all_by_user(db: Session, user_id, is_read: bool = None, page: int = 1, limit: int = 20):
        query = (
            db.query(Notification)
            .filter(Notification.user_reference_id == user_id)
        )
        if is_read is not None:
            query = query.filter(Notification.is_read == is_read)

        total = query.count()
        offset = (page - 1) * limit
        items = (
            query.order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    @staticmethod
    def count_unread(db: Session, user_id) -> int:
        return (
            db.query(Notification)
            .filter(
                Notification.user_reference_id == user_id,
                Notification.is_read == False  # noqa: E712
            )
            .count()
        )

    @staticmethod
    def mark_read(db: Session, notification: Notification) -> Notification:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notification)
        return notification

    @staticmethod
    def mark_all_read(db: Session, user_id) -> int:
        updated = (
            db.query(Notification)
            .filter(
                Notification.user_reference_id == user_id,
                Notification.is_read == False  # noqa: E712
            )
            .update(
                {"is_read": True, "read_at": datetime.now(timezone.utc)},
                synchronize_session=False
            )
        )
        db.commit()
        return updated
