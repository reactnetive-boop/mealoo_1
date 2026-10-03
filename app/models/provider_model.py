import uuid

from sqlalchemy import Column
from sqlalchemy import BigInteger
from sqlalchemy import String
from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Text
from sqlalchemy import Integer
from sqlalchemy import SmallInteger
from sqlalchemy import Enum

from sqlalchemy.dialects.postgresql import UUID

from datetime import datetime
from datetime import timezone

from app.core.database import Base
from app.models.mixins import AccountSecurityMixin
from enum import Enum as PyEnum
from sqlalchemy import UniqueConstraint

class MealServiceType(str, PyEnum):
    BREAKFAST = "Breakfast"
    LUNCH = "Lunch"
    DINNER = "Dinner"
    LUNCH_AND_DINNER = "Lunch and Dinner"
    LUNCH_AND_BREAKFAST = "Lunch and Breakfast"
    BREAKFAST_AND_DINNER = "Breakfast and Dinner"
    LUNCH_DINNER_BREAKFAST = "Lunch and Dinner and Breakfast"
    FULL_DAY = "Full Day"


class Provider(AccountSecurityMixin, Base):

    __tablename__ = "providers"

    __table_args__ = (
        UniqueConstraint("provider_id", name="uq_provider_provider_id"),
        {"schema": "provider"},
    )

    # Internal DB Primary Key
    id = Column(
        BigInteger,
        primary_key=True,
        index=True
    )

    # Public UUID
    provider_id = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False,
        index=True
    )

    mobile_number = Column(
        String,
        nullable=False,
        unique=True,
        index=True
    )

    hashed_password = Column(
        String,
        nullable=False
    )

    is_mobile_verified = Column(
        Boolean,
        default=False
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        server_default='true'
    )

    is_accepting_orders = Column(
        Boolean,
        default=True,
        nullable=False,
        server_default='true'
    )

    is_profile_completed = Column(
        Boolean,
        default=False
    )

    full_name = Column(
        String(128),
        nullable=True
    )

    business_name = Column(
        String(256),
        nullable=True
    )

    city = Column(
        String(128),
        nullable=True
    )

    area = Column(
        String(256),
        nullable=True
    )

    address = Column(
        Text,
        nullable=True
    )

    kitchen_type = Column(
        String(128),
        nullable=True
    )

    profile_image = Column(
        Text,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(
            timezone.utc
        )
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(
            timezone.utc
        ),
        onupdate=lambda: datetime.now(
            timezone.utc
        )
    )
    pincode = Column(
        Integer,
        nullable=True
    )
    house_no = Column(
        String(64),
        nullable=True
    )
    landmark = Column(
        String(128),
        nullable=True
    )
    state = Column(
        String(128),
        nullable=True
    )
    meal_service_type = Column(
        Enum(
            MealServiceType,
            values_callable=lambda x: [e.value for e in x],
            name="meal_service_type",
            schema="provider"
        ),
        nullable=True
    )

    # 14-digit FSSAI food business licence number
    fssai_licence = Column(
        String(14),
        nullable=True
    )

    # Max meals this provider can serve per individual meal-slot per day,
    # counted across ALL of the provider's packages.
    # NULL = no provider-level limit.
    daily_meal_quota = Column(
        SmallInteger,
        nullable=True
    )

    # Admin review of the kitchen: pending | approved | rejected.
    # A kitchen sells nothing until approved.
    approval_status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending"
    )

    # Reason shown to the kitchen when rejected
    approval_note = Column(
        Text,
        nullable=True
    )

    approved_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    approved_by = Column(
        UUID(as_uuid=True),
        nullable=True
    )
