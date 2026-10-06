import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class DevicePushToken(Base):
    """An app install that can receive push notifications (Expo push token)."""

    __tablename__ = "device_push_tokens"
    __table_args__ = (
        CheckConstraint("owner_type IN ('customer', 'provider', 'delivery_boy')", name="chk_push_owner_type"),
        Index("idx_push_tokens_owner", "owner_type", "owner_id"),
        {"schema": "auth"},
    )

    device_push_token_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    owner_type = Column(String(20), nullable=False)

    owner_id = Column(UUID(as_uuid=True), nullable=False)

    # one install = one token; re-registering moves it to the new owner
    token = Column(String(255), nullable=False, unique=True)

    platform = Column(String(20), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
