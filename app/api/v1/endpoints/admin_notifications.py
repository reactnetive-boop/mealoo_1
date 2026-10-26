from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.database import get_db
from app.core.errors import DomainError
from app.dependencies.auth_dependency import get_current_admin
from app.models.admin_notification_model import AdminNotification

router = APIRouter()


def _view(n: AdminNotification) -> dict:
    return {
        "notification_id": n.admin_notification_id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "data": n.data or {},
        "is_read": n.is_read,
        "read_at": n.read_at,
        "created_at": n.created_at,
    }


@router.get(
    "",
    summary="My Admin Notifications",
    description="Notices for the signed-in admin, newest first (e.g. a kitchen asked for a holiday), and `unread`.",
)
def list_notifications(unread_only: bool = Query(False), limit: int = Query(50, ge=1, le=200),
                       db: Session = Depends(get_db), current=Depends(get_current_admin)):
    q = db.query(AdminNotification).filter(AdminNotification.admin_user_reference_id == current["admin_id"])
    unread = q.filter(AdminNotification.is_read == False).count()  # noqa: E712
    if unread_only:
        q = q.filter(AdminNotification.is_read == False)  # noqa: E712
    rows = q.order_by(AdminNotification.created_at.desc()).limit(limit).all()
    return {"success": True, "unread": unread, "notifications": [_view(n) for n in rows]}


@router.put("/{notification_id}/read", summary="Mark an Admin Notification Read")
def mark_read(notification_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    n = db.query(AdminNotification).filter(
        AdminNotification.admin_notification_id == notification_id,
        AdminNotification.admin_user_reference_id == current["admin_id"],
    ).first()
    if n is None:
        raise DomainError("Notification not found", 404)
    if not n.is_read:
        n.is_read = True
        n.read_at = now_utc()
        db.commit()
    return {"success": True, "notification": _view(n)}


@router.put("/read-all", summary="Mark All Admin Notifications Read")
def mark_all_read(db: Session = Depends(get_db), current=Depends(get_current_admin)):
    count = db.query(AdminNotification).filter(
        AdminNotification.admin_user_reference_id == current["admin_id"],
        AdminNotification.is_read == False,  # noqa: E712
    ).update({"is_read": True, "read_at": now_utc()}, synchronize_session=False)
    db.commit()
    return {"success": True, "marked": count}
