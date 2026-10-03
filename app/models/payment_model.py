import uuid

from sqlalchemy import Column, String, Text, Numeric, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class Payment(Base):

    __tablename__ = "payments"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="chk_payment_amount"
        ),
        CheckConstraint(
            "subscription_reference_id IS NOT NULL OR extra_order_reference_id IS NOT NULL OR purpose = 'wallet_topup'",
            name="chk_payment_ref"
        ),
        UniqueConstraint("gateway_txn_id", name="payments_gateway_txn_id_key"),
        {"schema": "subscription"},
    )

    payment_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    subscription_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.subscription_id", name="payments_subscription_id_fkey"),
        nullable=True
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="payments_user_id_fkey"),
        nullable=False,
        index=True
    )

    extra_order_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.extra_orders.extra_order_id", name="payments_extra_order_id_fkey"),
        nullable=True
    )

    # 'subscription' | 'extra_order' | 'wallet_topup'
    purpose = Column(
        String(20),
        nullable=False,
        default="wallet_topup",
        server_default="wallet_topup"
    )

    amount = Column(
        Numeric(10, 2),
        nullable=False
    )

    # 'INR'
    currency = Column(
        String(3),
        default="INR"
    )

    # 'wallet' | 'upi' | 'card' | 'netbanking' | 'cash'
    method = Column(
        String(20),
        nullable=False
    )

    # 'pending' | 'completed' | 'failed' | 'refunded'
    status = Column(
        String(20),
        nullable=False,
        default="completed"
    )

    gateway = Column(
        String(50),
        nullable=True
    )

    gateway_order_id = Column(
        Text,
        nullable=True
    )

    gateway_txn_id = Column(
        Text,
        nullable=True
    )

    gateway_response = Column(
        JSONB,
        nullable=True
    )

    paid_at = Column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now()
    )

    refunded_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    refund_amount = Column(
        Numeric(10, 2),
        nullable=True
    )

    failure_reason = Column(
        Text,
        nullable=True
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

    # Deterministic key per business operation (e.g. "skip_refund:<order>").
    # Unique, so a retried or concurrent request can never post twice.
    idempotency_key = Column(
        String(120),
        nullable=True,
        unique=True
    )
