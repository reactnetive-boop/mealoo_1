"""Kitchen in-app notifications: list, mark read (own notifications only)."""

from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.models.provider_notification_model import ProviderNotification
from app.core.errors import DomainError


def _view(n: ProviderNotification) -> dict:
    return {
        "provider_notification_id": n.provider_notification_id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "data": n.data,
        "is_read": bool(n.is_read),
        "created_at": n.created_at,
    }


class ProviderNotificationService:

    @staticmethod
    def list(db: Session, provider_id: str, limit: int = 50, unread_only: bool = False):
        q = db.query(ProviderNotification).filter(ProviderNotification.provider_reference_id == provider_id)
        unread = q.filter(ProviderNotification.is_read.is_(False)).count()
        if unread_only:
            q = q.filter(ProviderNotification.is_read.is_(False))
        rows = q.order_by(ProviderNotification.created_at.desc()).limit(limit).all()
        return {"success": True, "total": len(rows), "unread": unread, "notifications": [_view(n) for n in rows]}

    @staticmethod
    def mark_read(db: Session, provider_id: str, notification_id):
        n = db.query(ProviderNotification).filter(
            ProviderNotification.provider_notification_id == notification_id,
            ProviderNotification.provider_reference_id == provider_id,
        ).first()
        if n is None:
            raise DomainError("Notification not found", 404)
        if not n.is_read:
            n.is_read = True
            n.read_at = now_utc()
            db.commit()
        return {"success": True, "message": "Notification marked as read"}

    @staticmethod
    def mark_all_read(db: Session, provider_id: str):
        updated = (
            db.query(ProviderNotification)
            .filter(ProviderNotification.provider_reference_id == provider_id, ProviderNotification.is_read.is_(False))
            .update({ProviderNotification.is_read: True, ProviderNotification.read_at: now_utc()}, synchronize_session=False)
        )
        db.commit()
        return {"success": True, "message": f"{updated} notifications marked as read"}
