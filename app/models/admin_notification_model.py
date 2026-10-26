import uuid

from sqlalchemy import Column, String, Boolean, Text, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class AdminNotification(Base):
    """
    In-app notices for the admin panel (e.g. a kitchen asked for a holiday).
    One row per admin, so each admin has their own read state.
    """

    __tablename__ = "admin_notifications"

    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_admin_notifications_dedupe"),
        Index("idx_admin_notifications_unread", "admin_user_reference_id", "is_read", "created_at"),
        {"schema": "master"},
    )

    admin_notification_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    admin_user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("master.admin_users.admin_user_id", name="admin_notifications_admin_id_fkey"),
        nullable=False,
    )

    # holiday_request | ...
    type = Column(String(50), nullable=False)
    title = Column(String(150), nullable=False)
    body = Column(Text, nullable=False)
    data = Column(JSONB, nullable=True)

    # one notice per event and admin
    dedupe_key = Column(String(200), nullable=True)

    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
