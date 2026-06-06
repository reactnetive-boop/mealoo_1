import uuid

from sqlalchemy import Column, String, Text, Numeric, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class Payment(Base):

    __tablename__ = "payments"

    __table_args__ = {
        "schema": "subscription"
    }

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    subscription_id = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    user_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True
    )

    extra_order_id = Column(
        UUID(as_uuid=True),
        nullable=True
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
