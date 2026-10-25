from sqlalchemy import (
    Column,
    String,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_user", "user_reference_id"),
        Index("idx_notifications_unread", "user_reference_id", "is_read"),
        Index("uq_notifications_dedupe", "dedupe_key", unique=True, postgresql_where=text("dedupe_key IS NOT NULL")),
        {"schema": "auth"},
    )

    notification_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "auth.users.user_id",
            name="notifications_user_id_fkey"
        ),
        nullable=False
    )

    type = Column(String(50), nullable=False)

    title = Column(String(150), nullable=False)

    body = Column(Text, nullable=False)

    data = Column(JSONB)

    is_read = Column(
        Boolean,
        default=False,
        nullable=False
    )

    read_at = Column(DateTime(timezone=True))

    sent_at = Column(DateTime(timezone=True))

    # one notice per business event (e.g. one per holiday-affected meal)
    dedupe_key = Column(String(150), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )