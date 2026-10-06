import uuid

from sqlalchemy import Column, String, Boolean, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class ProviderNotification(Base):
    """In-app notifications for kitchens (same shape as the customer / partner ones)."""

    __tablename__ = "provider_notifications"

    __table_args__ = (
        Index("idx_provider_notifications_provider", "provider_reference_id"),
        Index("idx_provider_notifications_unread", "provider_reference_id", "is_read"),
        {"schema": "provider"},
    )

    provider_notification_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="provider_notifications_provider_id_fkey"),
        nullable=False,
    )

    # new_subscription | new_order | partner_assigned | partner_unassigned |
    # pickup_pending | general
    type = Column(String(50), nullable=False)

    title = Column(String(150), nullable=False)

    body = Column(Text, nullable=False)

    data = Column(JSONB)

    is_read = Column(Boolean, default=False, nullable=False, server_default="false")

    read_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
