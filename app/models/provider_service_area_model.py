import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class ProviderServiceArea(Base):
    """An extra pincode a kitchen delivers to (its own pincode is always served)."""

    __tablename__ = "provider_service_areas"
    __table_args__ = (
        UniqueConstraint("provider_reference_id", "pincode", name="uq_provider_service_area"),
        {"schema": "provider"},
    )

    provider_service_area_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="provider_service_areas_provider_id_fkey"),
        nullable=False,
    )

    pincode = Column(Integer, nullable=False, index=True)

    created_by = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
