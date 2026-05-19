import uuid

from sqlalchemy import Column
from sqlalchemy import BigInteger
from sqlalchemy import String
from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Text
from sqlalchemy import Integer

from sqlalchemy.dialects.postgresql import UUID

from datetime import datetime
from datetime import timezone

from app.core.database import Base


class Provider(Base):

    __tablename__ = "providers"

    __table_args__ = {
        "schema": "provider"
    }

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
        Integer,
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

