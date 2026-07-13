import uuid

from sqlalchemy import Column, Numeric, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class DeliveryBoyWallet(Base):

    __tablename__ = "delivery_boy_wallets"

    __table_args__ = (
        CheckConstraint("balance >= 0", name="chk_delivery_boy_wallet_balance"),
        UniqueConstraint("delivery_boy_reference_id", name="delivery_boy_wallets_boy_id_key"),
        {"schema": "delivery"},
    )

    delivery_boy_wallet_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    delivery_boy_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "delivery.delivery_boys.delivery_boy_id",
            name="delivery_boy_wallets_delivery_boy_id_fkey"
        ),
        nullable=False,
        unique=True,
        index=True
    )

    balance = Column(
        Numeric(12, 2),
        default=0.00,
        nullable=False
    )

    total_earned = Column(
        Numeric(12, 2),
        default=0.00,
        nullable=False
    )

    total_withdrawn = Column(
        Numeric(12, 2),
        default=0.00,
        nullable=False
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
