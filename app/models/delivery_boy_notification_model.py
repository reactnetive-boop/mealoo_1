import uuid

from sqlalchemy import (
    Column,
    String,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class DeliveryBoyNotification(Base):

    __tablename__ = "delivery_boy_notifications"

    __table_args__ = (
        Index("idx_delivery_boy_notifications_boy", "delivery_boy_reference_id"),
        Index(
            "idx_delivery_boy_notifications_unread",
            "delivery_boy_reference_id", "is_read"
        ),
        {"schema": "delivery"},
    )

    delivery_boy_notification_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    delivery_boy_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "delivery.delivery_boys.delivery_boy_id",
            name="delivery_boy_notifications_delivery_boy_id_fkey"
        ),
        nullable=False
    )

    # order_assigned | order_delivered | payout | general
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

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
