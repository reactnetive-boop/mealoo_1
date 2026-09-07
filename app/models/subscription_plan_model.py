import uuid

from sqlalchemy import Column, String, SmallInteger, Numeric, Boolean, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class SubscriptionPlan(Base):

    __tablename__ = "subscription_plans"

    __table_args__ = (
        UniqueConstraint(
            "subscription_type",
            "meal_slot",
            name="subscription_plans_subscription_type_meal_slot_key"
        ),
        {"schema": "master"},
    )

    subscription_plan_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    # 'weekly' | 'monthly' | 'half_yearly' | 'yearly'
    subscription_type = Column(
        String(30),
        nullable=False
    )

    # 'breakfast' | 'lunch' | 'dinner'
    meal_slot = Column(
        String(20),
        nullable=False
    )

    duration_days = Column(
        SmallInteger,
        nullable=False
    )

    free_skips = Column(
        SmallInteger,
        default=0
    )

    discount_percent = Column(
        Numeric(5, 2),
        default=0.00
    )

    is_active = Column(
        Boolean,
        default=True
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
