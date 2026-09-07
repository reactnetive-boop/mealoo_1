from typing import List, Optional, Any, Dict
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    notification_id: UUID
    type: str
    title: str
    body: str
    data: Optional[Dict[str, Any]]
    is_read: bool
    read_at: Optional[datetime]
    sent_at: Optional[datetime]
    created_at: Optional[datetime]


class NotificationListResponse(BaseModel):

    success: bool
    total: int
    unread_count: int
    notifications: List[NotificationResponse]


class MarkNotificationReadResponse(BaseModel):

    success: bool
    message: str
