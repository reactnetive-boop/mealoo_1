import uuid

from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    Numeric,
    Text,
    ForeignKey,
    TIMESTAMP,
    Index
)

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.sql import func

from app.core.database import Base

from sqlalchemy.orm import relationship


class MenuPackage(Base):

    __tablename__ = "menu_packages"

    __table_args__ = (
        Index("idx_menu_packages_provider", "provider_id"),
        Index("idx_menu_packages_category", "category_reference_id"),
        Index("idx_menu_packages_active", "is_active"),
        Index("idx_menu_packages_available", "is_available"),
        {"schema": "master"},
    )

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
        nullable=False
    )

    category_reference_id = Column(
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

    is_predefined = Column(
        Boolean,
        server_default='false',
        default=False
    )

    is_active = Column(
        Boolean,
        server_default='false',
        default=False
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

    items = relationship(
        "MenuPackageItem",
        back_populates="menu_package",
        cascade="all, delete-orphan"
    )

    images = relationship(
        "MenuPackageImage",
        back_populates="menu_package",
        cascade="all, delete-orphan"
    )
    