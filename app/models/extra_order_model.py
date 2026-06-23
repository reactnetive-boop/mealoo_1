import uuid

from sqlalchemy import Column, String, Numeric, SmallInteger, Date, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class ExtraOrder(Base):

    __tablename__ = "extra_orders"

    __table_args__ = (
        CheckConstraint(
            "quantity >= 1 AND quantity <= 5",
            name="chk_extra_qty"
        ),
        Index("idx_extra_orders_user", "user_reference_id"),
        Index("idx_extra_orders_vendor", "vendor_reference_id"),
        {"schema": "subscription"},
    )

    extra_order_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="extra_orders_user_id_fkey"),
        nullable=False,
        index=True
    )

    vendor_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="extra_orders_vendor_id_fkey"),
        nullable=False
    )

    address_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.user_addresses.user_address_id", name="extra_orders_address_id_fkey"),
        nullable=False
    )

    package_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("master.menu_packages.package_id", name="extra_orders_package_id_fkey"),
        nullable=False
    )

    quantity = Column(
        SmallInteger,
        nullable=False,
        default=1
    )

    unit_price = Column(
        Numeric(10, 2),
        nullable=False
    )

    total_price = Column(
        Numeric(10, 2),
        nullable=False
    )

    delivery_date = Column(
        Date,
        nullable=False
    )

    # 'breakfast' | 'lunch' | 'dinner'
    meal_slot = Column(
        String(20),
        nullable=False
    )

    delivery_boy_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("delivery.delivery_boys.delivery_boy_id", name="extra_orders_delivery_boy_id_fkey"),
        nullable=True,
        index=True
    )

    # 'pending' | 'confirmed' | 'preparing' | 'out_for_delivery' | 'delivered' | 'cancelled'
    status = Column(
        String(30),
        nullable=False,
        default="pending"
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
