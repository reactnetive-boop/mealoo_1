import uuid

from sqlalchemy import (
    Column, String, Boolean, Date, DateTime, Text, Numeric, SmallInteger,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class Order(Base):

    __tablename__ = "orders"

    __table_args__ = (
        UniqueConstraint(
            "subscription_reference_id", "order_date", "meal_slot",
            name="orders_subscription_id_order_date_meal_slot_key"
        ),
        Index("idx_orders_sub", "subscription_reference_id"),
        Index("idx_orders_user", "user_reference_id"),
        Index("idx_orders_vendor", "vendor_reference_id"),
        Index("idx_orders_date_status", "order_date", "status"),
        {"schema": "subscription"},
    )

    order_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    subscription_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.subscription_id", name="orders_subscription_id_fkey"),
        nullable=False
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="orders_user_id_fkey"),
        nullable=False
    )

    vendor_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="orders_vendor_id_fkey"),
        nullable=False
    )

    delivery_address_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.user_addresses.user_address_id", name="orders_delivery_address_id_fkey"),
        nullable=False
    )

    order_date = Column(
        Date,
        nullable=False
    )

    # 'lunch' | 'dinner' | 'both'
    meal_slot = Column(
        String(20),
        nullable=False
    )

    # scheduled -> preparing -> ready_for_pickup -> picked_up -> out_for_delivery
    # -> delivered; or skipped | cancelled (see app/domain/status.py)
    status = Column(
        String(30),
        nullable=False,
        default="scheduled"
    )

    is_free_skip = Column(
        Boolean,
        default=False,
        nullable=False
    )

    skip_requested_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    skip_deadline = Column(
        DateTime(timezone=True),
        nullable=True
    )

    delivered_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    delivery_notes = Column(
        Text,
        nullable=True
    )

    delivery_boy_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("delivery.delivery_boys.delivery_boy_id", name="orders_delivery_boy_id_fkey"),
        nullable=True,
        index=True
    )

    # Legacy plaintext delivery code (rows created before delivery_code_seed).
    # New rows leave it empty: the code is derived from delivery_code_seed.
    otp_for_delivery = Column(
        String(6),
        nullable=True
    )

    # Random seed the customer's 6-digit delivery code is derived from with a
    # server-side key (app/domain/verification.py); the code is never stored.
    delivery_code_seed = Column(
        String(64),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Failed customer-code attempts; delivery locks once the limit is hit
    delivery_code_attempts = Column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0"
    )

    # Retired per-order kitchen code; pickup now uses the kitchen's daily code
    # (provider.provider_pickup_codes). Kept for history / downgrade only.
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

    # Partner left the kitchen for the customer ("Start delivery")
    out_for_delivery_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # Partner reported reaching the customer (customer is notified once)
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
