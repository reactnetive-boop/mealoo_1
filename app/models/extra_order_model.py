import uuid

from sqlalchemy import Column, String, Numeric, SmallInteger, Date, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
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

    # pending -> confirmed -> preparing -> ready_for_pickup -> picked_up ->
    # out_for_delivery -> delivered; or cancelled (see app/domain/status.py)
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

    # Legacy plaintext delivery code (rows created before delivery_code_seed)
    otp_for_delivery = Column(
        String(6),
        nullable=True
    )

    # Seed of the customer's 6-digit delivery code (app/domain/verification.py)
    delivery_code_seed = Column(
        String(64),
        nullable=True
    )

    delivered_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # Groups the rows of one checkout (one wallet debit)
    checkout_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True
    )

    # Charges included in total_price; breakdown frozen at order time
    charges_amount = Column(
        Numeric(10, 2),
        nullable=False,
        default=0,
        server_default="0"
    )

    pricing_snapshot = Column(
        JSONB,
        nullable=True
    )

    # Failed customer-code attempts; delivery locks once the limit is hit
    delivery_code_attempts = Column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0"
    )

    # Retired per-order kitchen code; pickup now uses the kitchen's daily code
    pickup_code = Column(
        String(6),
        nullable=True
    )

    # Failed kitchen pickup-code attempts; pickup locks once the limit is hit
    pickup_code_attempts = Column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0"
    )

    picked_up_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    out_for_delivery_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    arrived_at = Column(
        DateTime(timezone=True),
        nullable=True
    )


    # The partner reached the address but could not hand over (customer away,
    # wrong address, refused); see DeliveryBoyOrderService.fail_delivery
    failed_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(String(40), nullable=True)

    # Why the order was cancelled: paused | subscription_cancelled |
    # switched | kitchen_holiday | rejected_by_kitchen | customer | admin
    cancel_reason = Column(
        String(50),
        nullable=True
    )

    # Set once the meal's value is returned to the customer's wallet
    refund_amount = Column(
        Numeric(10, 2),
        nullable=True
    )

    refunded_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # Set once kitchen / partner / platform earnings are booked
    settled_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
