import uuid

from sqlalchemy import Column, String, Text, Numeric, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class DeliveryBoyWalletTransaction(Base):

    __tablename__ = "delivery_boy_wallet_transactions"

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_delivery_boy_wtxn_amount"),
        Index("idx_delivery_boy_wtxn_boy", "delivery_boy_reference_id"),
        Index("idx_delivery_boy_wtxn_wallet", "wallet_reference_id"),
        Index("idx_delivery_boy_wtxn_type", "type"),
        {"schema": "delivery"},
    )

    delivery_boy_wallet_transaction_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    wallet_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "delivery.delivery_boy_wallets.delivery_boy_wallet_id",
            name="delivery_boy_wtxn_wallet_id_fkey"
        ),
        nullable=False
    )

    delivery_boy_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "delivery.delivery_boys.delivery_boy_id",
            name="delivery_boy_wtxn_delivery_boy_id_fkey"
        ),
        nullable=False,
        index=True
    )

    # 'credit' | 'debit'
    type = Column(
        String(20),
        nullable=False
    )

    # credit: 'delivery_payout' | 'adjustment' | 'manual_credit'
    # debit : 'withdrawal' | 'penalty'
    reason = Column(
        String(50),
        nullable=False
    )

    amount = Column(
        Numeric(12, 2),
        nullable=False
    )

    balance_before = Column(
        Numeric(12, 2),
        nullable=False
    )

    balance_after = Column(
        Numeric(12, 2),
        nullable=False
    )

    # order_id / extra_order_id
    reference_id = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    # 'order' | 'extra_order' | 'withdrawal'
    reference_type = Column(
        String(50),
        nullable=True
    )

    description = Column(
        Text,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
