import uuid

from sqlalchemy import Column, Numeric, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class ProviderWallet(Base):

    __tablename__ = "provider_wallets"

    __table_args__ = (
        CheckConstraint("balance >= 0", name="chk_provider_wallet_balance"),
        UniqueConstraint("provider_reference_id", name="provider_wallets_provider_id_key"),
        {"schema": "provider"},
    )

    provider_wallet_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="provider_wallets_provider_id_fkey"),
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
