import uuid

from sqlalchemy import Column, String, Text, Numeric, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class ProviderWalletTransaction(Base):

    __tablename__ = "provider_wallet_transactions"

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_provider_wtxn_amount"),
        Index("idx_provider_wtxn_provider", "provider_reference_id"),
        Index("idx_provider_wtxn_wallet", "wallet_reference_id"),
        Index("idx_provider_wtxn_type", "type"),
        {"schema": "provider"},
    )

    provider_wallet_transaction_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    wallet_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.provider_wallets.provider_wallet_id", name="provider_wallet_txn_wallet_id_fkey"),
        nullable=False
    )

    provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="provider_wallet_txn_provider_id_fkey"),
        nullable=False,
        index=True
    )

    # 'credit' | 'debit'
    type = Column(
        String(20),
        nullable=False
    )

    # credit: 'order_delivered' | 'adjustment' | 'manual_credit'
    # debit : 'withdrawal' | 'refund_issued' | 'penalty'
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

    # order_id / subscription_id / extra_order_id
    reference_id = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    # 'order' | 'extra_order' | 'subscription' | 'withdrawal'
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
