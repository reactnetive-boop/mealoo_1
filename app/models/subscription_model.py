import uuid

from sqlalchemy import Column, String, SmallInteger, Integer, Numeric, Text, Date, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.core.database import Base


class Subscription(Base):

    __tablename__ = "subscriptions"

    __table_args__ = (
        CheckConstraint("final_amount > 0", name="chk_sub_amount"),
        CheckConstraint("end_date > start_date", name="chk_sub_dates"),
        CheckConstraint("free_skips_used <= free_skips_total", name="chk_sub_skips"),
        Index("idx_subscriptions_user", "user_reference_id"),
        Index("idx_subscriptions_vendor", "vendor_reference_id"),
        Index("idx_subscriptions_status", "status"),
        Index("idx_subscriptions_dates", "start_date", "end_date"),
        {"schema": "subscription"},
    )

    subscription_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="subscriptions_user_id_fkey"),
        nullable=False,
        index=True
    )

    vendor_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="subscriptions_vendor_id_fkey"),
        nullable=False
    )

    plan_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("master.subscription_plans.subscription_plan_id", name="subscriptions_plan_id_fkey"),
        nullable=False
    )

    user_address_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.user_addresses.user_address_id", name="subscriptions_user_address_id_fkey"),
        nullable=False
    )

    # 'pending' | 'active' | 'paused' | 'cancelled' | 'expired' | 'switched'
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

    # Set when subscription is paused; cleared on resume
    pause_start_date = Column(
        Date,
        nullable=True
    )

    # Cumulative calendar days paused across all pause/resume cycles
    total_days_paused = Column(
        Integer,
        nullable=False,
        default=0
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
