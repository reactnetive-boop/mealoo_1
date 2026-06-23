import uuid

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func

from app.core.database import Base


class ProviderComplaint(Base):

    __tablename__ = "provider_complaints"

    __table_args__ = (
        Index("idx_provider_complaints_provider", "provider_reference_id"),
        Index("idx_provider_complaints_against", "against"),
        Index("idx_provider_complaints_status", "status"),
        Index("idx_provider_complaints_delivery_boy", "delivery_boy_reference_id"),
        {"schema": "provider"},
    )

    provider_complaint_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="provider_complaints_provider_id_fkey"),
        nullable=False,
        index=True
    )

    # 'platform' | 'delivery_boy'
    against = Column(String(30), nullable=False)

    # Required when against = 'delivery_boy'
    delivery_boy_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "delivery.delivery_boys.delivery_boy_id",
            name="provider_complaints_delivery_boy_id_fkey"
        ),
        nullable=True
    )

    # Optional reference to a specific order or extra order
    order_id = Column(UUID(as_uuid=True), nullable=True)

    # 'order' | 'extra_order'
    order_type = Column(String(20), nullable=True)

    # 'open' | 'in_progress' | 'resolved' | 'closed' | 'rejected'
    status = Column(String(20), nullable=False, default="open")

    subject = Column(String(255), nullable=False)

    description = Column(Text, nullable=False)

    evidence_urls = Column(ARRAY(Text), nullable=True, default=[])

    admin_notes = Column(Text, nullable=True)

    resolved_by = Column(UUID(as_uuid=True), nullable=True)

    resolution = Column(Text, nullable=True)

    resolved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
