import uuid

from sqlalchemy import (
    Column, String, Boolean, Date, DateTime, Text,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class Order(Base):

    __tablename__ = "orders"

    __table_args__ = (
        UniqueConstraint(
            "subscription_reference_id", "order_date", "meal_slot",
            name="orders_subscription_id_order_date_meal_slot_key"
        ),
        Index("idx_orders_sub", "subscription_reference_id"),
        Index("idx_orders_user", "user_reference_id"),
        Index("idx_orders_vendor", "vendor_reference_id"),
        Index("idx_orders_date_status", "order_date", "status"),
        {"schema": "subscription"},
    )

    order_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    subscription_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.subscription_id", name="orders_subscription_id_fkey"),
        nullable=False
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="orders_user_id_fkey"),
        nullable=False
    )

    vendor_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="orders_vendor_id_fkey"),
        nullable=False
    )

    delivery_address_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.user_addresses.user_address_id", name="orders_delivery_address_id_fkey"),
        nullable=False
    )

    order_date = Column(
        Date,
        nullable=False
    )

    # 'lunch' | 'dinner' | 'both'
    meal_slot = Column(
        String(20),
        nullable=False
    )

    # 'scheduled' | 'preparing' | 'out_for_delivery' | 'delivered' | 'skipped' | 'cancelled'
    status = Column(
        String(30),
        nullable=False,
        default="scheduled"
    )

    is_free_skip = Column(
        Boolean,
        default=False,
        nullable=False
    )

    skip_requested_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    skip_deadline = Column(
        DateTime(timezone=True),
        nullable=True
    )

    delivered_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    delivery_notes = Column(
        Text,
        nullable=True
    )

    delivery_boy_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("delivery.delivery_boys.delivery_boy_id", name="orders_delivery_boy_id_fkey"),
        nullable=True,
        index=True
    )

    otp_for_delivery = Column(
        String(6),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
