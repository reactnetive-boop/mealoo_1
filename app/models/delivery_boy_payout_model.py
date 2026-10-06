import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.crypto import EncryptedString
from app.core.database import Base


class DeliveryBoyPayoutDetails(Base):

    __tablename__ = "delivery_boy_payout_details"

    __table_args__ = (
        UniqueConstraint(
            "delivery_boy_reference_id",
            name="uq_delivery_boy_payout_boy"
        ),
        {"schema": "delivery"},
    )

    delivery_boy_payout_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    delivery_boy_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "delivery.delivery_boys.delivery_boy_id",
            name="delivery_boy_payout_delivery_boy_id_fkey"
        ),
        nullable=False,
        unique=True,
        index=True
    )

    # Bank transfer details — all optional so a partner can save UPI only.
    account_holder_name = Column(String(128), nullable=True)

    # encrypted at rest (app.core.crypto)
    account_number = Column(EncryptedString, nullable=True)

    ifsc_code = Column(String(20), nullable=True)

    bank_name = Column(String(128), nullable=True)

    upi_id = Column(String(128), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
