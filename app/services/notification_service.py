from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.notification_repository import NotificationRepository


class NotificationService:

    @staticmethod
    def create_notification(
        db: Session,
        user_id: str,
        type: str,
        title: str,
        body: str,
        data: dict = None
    ):
        return NotificationRepository.create(db, {
            "user_reference_id": user_id,
            "type": type,
            "title": title,
            "body": body,
            "data": data
        })

    @staticmethod
    def list_notifications(
        db: Session,
        user_id: str,
        is_read: bool = None,
        page: int = 1,
        limit: int = 20
    ):
        items, total = NotificationRepository.get_all_by_user(
            db, user_id, is_read=is_read, page=page, limit=limit
        )
        unread_count = NotificationRepository.count_unread(db, user_id)

        return {
            "success": True,
            "total": total,
            "unread_count": unread_count,
            "notifications": items
        }

    @staticmethod
    def mark_as_read(db: Session, user_id: str, notification_id):
        notification = NotificationRepository.get_by_id_and_user(db, notification_id, user_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        NotificationRepository.mark_read(db, notification)

        return {"success": True, "message": "Notification marked as read"}

    @staticmethod
    def mark_all_as_read(db: Session, user_id: str):
        updated = NotificationRepository.mark_all_read(db, user_id)

        return {"success": True, "message": f"Marked {updated} notification(s) as read"}
