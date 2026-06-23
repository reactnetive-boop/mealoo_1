import uuid

from sqlalchemy import Column, String, Text, Boolean, DateTime, Numeric, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID

from datetime import datetime, timezone

from app.core.database import Base


class UserAddress(Base):

    __tablename__ = "user_addresses"

    __table_args__ = (
        CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="user_addresses_latitude_check"
        ),
        CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="user_addresses_longitude_check"
        ),
        Index("idx_user_addresses_user", "user_reference_id"),
        Index("idx_user_addresses_pincode", "pin_code"),
        {"schema": "auth"},
    )

    user_address_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="user_addresses_user_id_fkey"),
        nullable=False,
        index=True
    )

    label = Column(
        String(50),
        nullable=True
    )

    address_line1 = Column(
        Text,
        nullable=False
    )

    address_line2 = Column(
        Text,
        nullable=True
    )

    landmark = Column(
        Text,
        nullable=True
    )

    city = Column(
        String(100),
        nullable=False
    )

    state = Column(
        String(100),
        nullable=False
    )

    pin_code = Column(
        String(10),
        nullable=False
    )

    country = Column(
        String(6),
        nullable=True,
        default="IN"
    )

    latitude = Column(
        Numeric(9, 6),
        nullable=True
    )

    longitude = Column(
        Numeric(10, 6),
        nullable=True
    )

    is_default = Column(
        Boolean,
        default=False
    )

    is_active = Column(
        Boolean,
        default=True
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
