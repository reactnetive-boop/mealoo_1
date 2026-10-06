import uuid

from sqlalchemy import Column, String, Numeric, Text, DateTime, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class PayoutRequest(Base):
    """
    A kitchen's or delivery partner's request to withdraw wallet balance.

    The amount is held (debited) from the wallet when requested so it cannot
    be spent twice; an admin marks it paid after the offline bank transfer, or
    rejects it, which returns the hold to the wallet.
    """

    __tablename__ = "payout_requests"

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_payout_request_amount"),
        CheckConstraint("owner_type IN ('provider', 'delivery_boy', 'customer')", name="chk_payout_owner_type"),
        CheckConstraint("status IN ('pending', 'paid', 'rejected')", name="chk_payout_status"),
        Index("idx_payout_requests_owner", "owner_type", "owner_id"),
        Index("idx_payout_requests_status", "status"),
        {"schema": "subscription"},
    )

    payout_request_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    owner_type = Column(String(20), nullable=False)

    owner_id = Column(UUID(as_uuid=True), nullable=False)

    amount = Column(Numeric(12, 2), nullable=False)

    status = Column(String(20), nullable=False, default="pending")

    note = Column(Text, nullable=True)

    admin_note = Column(Text, nullable=True)

    # Bank / UPI transaction reference entered by the admin when paid
    payout_reference = Column(String(120), nullable=True)

    requested_at = Column(DateTime(timezone=True), server_default=func.now())

    processed_at = Column(DateTime(timezone=True), nullable=True)

    processed_by = Column(UUID(as_uuid=True), nullable=True)
