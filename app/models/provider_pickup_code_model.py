import uuid

from sqlalchemy import Column, String, SmallInteger, Date, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class ProviderPickupCode(Base):
    """
    A kitchen's pickup code for one business day.

    The code itself is never stored: `code_seed` is random and the 6-digit
    code is derived from it with a server-side key (app/domain/verification.py),
    so a database copy reveals no codes. Regenerating replaces the seed and
    bumps `version`, which invalidates the previous code at once.
    """

    __tablename__ = "provider_pickup_codes"

    __table_args__ = (
        UniqueConstraint("provider_reference_id", "code_date", name="uq_provider_pickup_code_day"),
        CheckConstraint("status IN ('active', 'revoked')", name="chk_pickup_code_status"),
        {"schema": "provider"},
    )

    pickup_code_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="provider_pickup_codes_provider_id_fkey"),
        nullable=False,
    )

    # Business-local (IST) date the code is valid for
    code_date = Column(Date, nullable=False)

    code_seed = Column(String(64), nullable=False)

    version = Column(SmallInteger, nullable=False, default=1, server_default="1")

    # active | revoked
    status = Column(String(20), nullable=False, default="active", server_default="active")

    # End of code_date in the business timezone
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # system (daily job / first use) | provider (regenerated)
    created_by_type = Column(String(20), nullable=False, default="system", server_default="system")

    regenerated_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
