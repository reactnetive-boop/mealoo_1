import uuid

from sqlalchemy import Column, String, Numeric, Text, DateTime, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class PlatformLedgerEntry(Base):
    """
    Orleeno's own side of every delivered meal: revenue (commission and
    charges) and costs (partner payout, plan discounts it funds). Together with
    the customer, kitchen and partner wallet ledgers this makes every rupee
    traceable.
    """

    __tablename__ = "platform_ledger_entries"

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_platform_ledger_amount"),
        CheckConstraint("direction IN ('credit', 'debit')", name="chk_platform_ledger_direction"),
        Index("idx_platform_ledger_reference", "reference_type", "reference_id"),
        Index("idx_platform_ledger_type", "entry_type"),
        {"schema": "subscription"},
    )

    platform_ledger_entry_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # commission | sms_charge | payment_gateway_charge | packaging_charge |
    # delivery_charge | delivery_partner_payout | plan_discount
    entry_type = Column(String(40), nullable=False)

    # credit = revenue to Orleeno, debit = cost borne by Orleeno
    direction = Column(String(10), nullable=False)

    amount = Column(Numeric(12, 2), nullable=False)

    # order | extra_order
    reference_type = Column(String(30), nullable=False)

    reference_id = Column(UUID(as_uuid=True), nullable=False)

    description = Column(Text, nullable=True)

    idempotency_key = Column(String(120), nullable=False, unique=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
