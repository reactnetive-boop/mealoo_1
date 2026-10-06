import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.crypto import EncryptedString
from app.core.database import Base


class ProviderPayoutDetails(Base):
    """Where Orleeno sends a kitchen's withdrawals (bank account and / or UPI)."""

    __tablename__ = "provider_payout_details"
    __table_args__ = {"schema": "provider"}

    provider_payout_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="provider_payout_provider_id_fkey"),
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
