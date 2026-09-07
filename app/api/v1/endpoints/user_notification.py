from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.notification_schema import (
    NotificationListResponse,
    MarkNotificationReadResponse
)
from app.services.notification_service import NotificationService

router = APIRouter()


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List My Notifications",
    description=(
        "**Fetch the logged-in user's notifications, newest first.**\n\n"
        "Filter by `is_read` to show only unread or only read notifications. "
        "Response includes `unread_count` for a notification badge.\n\n"
        "**When to call:** On the notifications screen, or on app open to show the unread badge."
    )
)
def list_notifications(
    is_read: Optional[bool] = Query(None, description="Filter by read/unread status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return NotificationService.list_notifications(
        db,
        current_user["user_id"],
        is_read=is_read,
        page=page,
        limit=limit
    )


@router.put(
    "/{notification_id}/read",
    response_model=MarkNotificationReadResponse,
    summary="Mark Notification as Read",
    description=(
        "**Mark a single notification as read.**\n\n"
        "**When to call:** When the user taps/opens a notification."
    )
)
def mark_as_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return NotificationService.mark_as_read(
        db,
        current_user["user_id"],
        notification_id
    )


@router.put(
    "/read-all",
    response_model=MarkNotificationReadResponse,
    summary="Mark All Notifications as Read",
    description=(
        "**Mark every unread notification for this user as read.**\n\n"
        "**When to call:** When the user taps 'Mark all as read' on the notifications screen."
    )
)
def mark_all_as_read(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return NotificationService.mark_all_as_read(
        db,
        current_user["user_id"]
    )
