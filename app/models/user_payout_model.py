import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.crypto import EncryptedString
from app.core.database import Base


class UserPayoutDetails(Base):
    """Where a customer's wallet withdrawals are sent (bank account and / or UPI)."""

    __tablename__ = "user_payout_details"
    __table_args__ = {"schema": "auth"}

    user_payout_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="user_payout_user_id_fkey"),
        nullable=False,
        unique=True,
    )

    account_holder_name = Column(String(128), nullable=True)

    # encrypted at rest (app.core.crypto)
    account_number = Column(EncryptedString, nullable=True)

    ifsc_code = Column(String(20), nullable=True)

    bank_name = Column(String(128), nullable=True)

    upi_id = Column(String(128), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
