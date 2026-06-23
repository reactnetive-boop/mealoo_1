import uuid

from sqlalchemy import Column, String, Text, Numeric, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class WalletTransaction(Base):

    __tablename__ = "wallet_transactions"

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_wtxn_amount"),
        Index("idx_wallet_txn_user", "user_reference_id"),
        Index("idx_wallet_txn_wallet", "wallet_reference_id"),
        {"schema": "subscription"},
    )

    wallet_transaction_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    wallet_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.wallets.wallet_id", name="wallet_transactions_wallet_id_fkey"),
        nullable=False
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="wallet_transactions_user_id_fkey"),
        nullable=False,
        index=True
    )

    # 'credit' | 'debit'
    type = Column(
        String(20),
        nullable=False
    )

    # 'order_placed' | 'order_cancelled' | 'topup' | 'refund'
    reason = Column(
        String(50),
        nullable=False
    )

    amount = Column(
        Numeric(10, 2),
        nullable=False
    )

    balance_before = Column(
        Numeric(10, 2),
        nullable=False
    )

    balance_after = Column(
        Numeric(10, 2),
        nullable=False
    )

    reference_id = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    reference_type = Column(
        String(50),
        nullable=True
    )

    description = Column(
        Text,
        nullable=True
    )

    created_by = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
