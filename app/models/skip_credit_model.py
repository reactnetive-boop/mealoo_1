import uuid

from sqlalchemy import Column, String, Text, Date, DateTime, SmallInteger, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class SkipCreditTransaction(Base):
    """
    Skip wallet ledger: every extra free skip granted to a subscription (e.g.
    VENDOR_EMERGENCY_HOLIDAY_COMPENSATION), with the free-skip balance before
    and after. The idempotency key is unique, so a retry never grants twice.
    """

    __tablename__ = "skip_credit_transactions"

    __table_args__ = (
        CheckConstraint("skips > 0", name="chk_skip_credit_positive"),
        CheckConstraint("type IN ('credit', 'debit')", name="chk_skip_credit_type"),
        Index("idx_skip_credit_subscription", "subscription_reference_id"),
        {"schema": "subscription"},
    )

    skip_credit_transaction_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    subscription_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.subscription_id", name="skip_credit_txn_subscription_id_fkey"),
        nullable=False,
    )
    user_reference_id = Column(
        UUID(as_uuid=True), ForeignKey("auth.users.user_id", name="skip_credit_txn_user_id_fkey"), nullable=False,
    )
    order_reference_id = Column(
        UUID(as_uuid=True), ForeignKey("subscription.orders.order_id", name="skip_credit_txn_order_id_fkey"),
        nullable=True,
    )
    vendor_reference_id = Column(
        UUID(as_uuid=True), ForeignKey("provider.providers.provider_id", name="skip_credit_txn_vendor_id_fkey"),
        nullable=True,
    )
    meal_date = Column(Date, nullable=True)

    type = Column(String(10), nullable=False, default="credit")
    skips = Column(SmallInteger, nullable=False)
    reason = Column(String(60), nullable=False)

    free_skips_before = Column(SmallInteger, nullable=False)
    free_skips_after = Column(SmallInteger, nullable=False)

    reference_type = Column(String(50), nullable=True)
    reference_id = Column(UUID(as_uuid=True), nullable=True)
    description = Column(Text, nullable=True)

    idempotency_key = Column(String(120), nullable=False, unique=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
