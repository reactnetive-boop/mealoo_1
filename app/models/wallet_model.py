import uuid

from sqlalchemy import Column, Numeric, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class Wallet(Base):

    __tablename__ = "wallets"

    __table_args__ = (
        CheckConstraint("balance >= 0", name="chk_wallet_balance"),
        UniqueConstraint("user_reference_id", name="wallets_user_id_key"),
        {"schema": "subscription"},
    )

    wallet_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="wallets_user_id_fkey"),
        nullable=False,
        unique=True,
        index=True
    )

    balance = Column(
        Numeric(10, 2),
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
