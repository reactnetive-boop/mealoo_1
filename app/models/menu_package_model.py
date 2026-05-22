import uuid

from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    Numeric,
    Text,
    ForeignKey,
    TIMESTAMP
)

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.sql import func

from app.core.database import Base


class MenuPackage(Base):

    __tablename__ = "menu_packages"

    __table_args__ = {
        "schema": "master"
    }

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    package_id = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )

    provider_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "provider.providers.provider_id"
        ),
        nullable=False
    )

    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "master.menu_categories.category_id"
        ),
        nullable=False
    )

    package_name = Column(
        String(255),
        nullable=False
    )

    short_description = Column(
        String(500)
    )

    description = Column(
        Text
    )

    meal_type = Column(
        String(50)
    )

    food_type = Column(
        String(50)
    )

    price = Column(
        Numeric(10, 2),
        nullable=False
    )

    discounted_price = Column(
        Numeric(10, 2)
    )

    is_subscription_available = Column(
        Boolean,
        default=False
    )

    subscription_price = Column(
        Numeric(10, 2)
    )

    is_available = Column(
        Boolean,
        default=True
    )

    is_active = Column(
        Boolean,
        default=True
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )