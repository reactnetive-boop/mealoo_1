import uuid

from sqlalchemy import (
    Column,
    SmallInteger,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class CartItem(Base):

    __tablename__ = "cart_items"

    __table_args__ = (
        UniqueConstraint(
            "user_reference_id",
            "package_reference_id",
            name="uq_cart_user_package",
        ),
        CheckConstraint(
            "quantity >= 1 AND quantity <= 10",
            name="chk_cart_qty",
        ),
        Index("idx_cart_items_user", "user_reference_id"),
        {"schema": "subscription"},
    )

    cart_item_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="cart_items_user_id_fkey"),
        nullable=False,
    )

    vendor_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="cart_items_vendor_id_fkey"),
        nullable=False,
    )

    package_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("master.menu_packages.package_id", name="cart_items_package_id_fkey"),
        nullable=False,
    )

    quantity = Column(
        SmallInteger,
        nullable=False,
        default=1,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    package = relationship(
        "MenuPackage",
        primaryjoin="CartItem.package_reference_id == MenuPackage.package_id",
        foreign_keys="[CartItem.package_reference_id]",
        viewonly=True,
        lazy="joined",
    )
