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

from sqlalchemy.dialects.postgresql import JSONB, UUID

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

    # The kitchen that owns the package; NULL for Orleeno catalogue packages
    # (is_predefined), which kitchens offer through provider_selected_packages.
    provider_id = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    # Admin who created a catalogue package
    created_by_admin_id = Column(UUID(as_uuid=True), nullable=True)

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

    # Admin review: pending | approved | rejected. is_active is the admin's
    # on/off switch for an approved package; deleted_at is the kitchen's
    # soft delete. A package is sellable only when approved, active,
    # available and not deleted.
    approval_status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending"
    )

    approval_note = Column(
        Text,
        nullable=True
    )

    approved_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True
    )

    approved_by = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    deleted_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True
    )

    # A kitchen's edit of an approved (live) package waits here for review
    # while the approved version stays on sale: {"fields": {...}, "items":
    # [{item_id, item_name, quantity, item_order}] | absent}.
    pending_changes = Column(JSONB, nullable=True)

    pending_changes_at = Column(TIMESTAMP(timezone=True), nullable=True)
