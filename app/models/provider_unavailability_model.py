
from sqlalchemy import Column, Integer, Date, Text, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class ProviderUnavailability(Base):

    __tablename__ = "provider_unavailability"

    __table_args__ = (
        UniqueConstraint("provider_reference_id", "unavailable_date", name="uq_provider_unavailability_date"),
        Index("idx_provider_unavail_date", "provider_reference_id", "unavailable_date"),
        {"schema": "provider"},
    )

    provider_unavailability_id = Column(Integer, primary_key=True, index=True)

    provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="provider_unavail_provider_id_fkey"),
        nullable=False,
        index=True
    )

    unavailable_date = Column(Date, nullable=False)

    reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
