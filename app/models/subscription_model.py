import uuid

from sqlalchemy import Column, String, SmallInteger, Numeric, Text, Date, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.core.database import Base


class Subscription(Base):

    __tablename__ = "subscriptions"

    __table_args__ = {
        "schema": "subscription"
    }

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    user_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True
    )

    vendor_id = Column(
        UUID(as_uuid=True),
        nullable=False
    )

    plan_id = Column(
        UUID(as_uuid=True),
        nullable=False
    )

    user_address_id = Column(
        UUID(as_uuid=True),
        nullable=False
    )

    # 'pending' | 'active' | 'paused' | 'cancelled' | 'expired'
    status = Column(
        String(20),
        nullable=False,
        default="active"
    )

    # 'breakfast' | 'lunch' | 'dinner'
    meal_slot = Column(
        String(20),
        nullable=False
    )

    # 'weekly' | 'monthly' | 'half_yearly' | 'yearly'
    subscription_type = Column(
        String(30),
        nullable=False
    )

    start_date = Column(
        Date,
        nullable=False
    )

    end_date = Column(
        Date,
        nullable=False
    )

    free_skips_total = Column(
        SmallInteger,
        default=0
    )

    free_skips_used = Column(
        SmallInteger,
        default=0
    )

    total_amount = Column(
        Numeric(10, 2),
        nullable=False
    )

    discount_amount = Column(
        Numeric(10, 2),
        default=0.00
    )

    final_amount = Column(
        Numeric(10, 2),
        nullable=False
    )

    notes = Column(
        Text,
        nullable=True
    )

    cancelled_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    cancel_reason = Column(
        Text,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    packages = relationship(
        "SubscriptionPackage",
        back_populates="subscription",
        cascade="all, delete-orphan"
    )
