import uuid

from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class DeliveryBoyDocument(Base):

    __tablename__ = "delivery_boy_documents"

    __table_args__ = (
        # One row per document type per delivery boy — re-upload replaces it.
        UniqueConstraint(
            "delivery_boy_reference_id", "document_type",
            name="uq_delivery_boy_document_type"
        ),
        Index("idx_delivery_boy_documents_boy", "delivery_boy_reference_id"),
        {"schema": "delivery"},
    )

    delivery_boy_document_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    delivery_boy_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "delivery.delivery_boys.delivery_boy_id",
            name="delivery_boy_documents_delivery_boy_id_fkey"
        ),
        nullable=False
    )

    # aadhaar | pan | driving_license | vehicle_rc
    document_type = Column(String(50), nullable=False)

    file_url = Column(Text, nullable=False)

    # pending | verified | rejected  (admin verifies later)
    status = Column(String(20), nullable=False, server_default="pending")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Reviewer's note, shown to the partner when a document is rejected
    remarks = Column(Text, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(UUID(as_uuid=True), nullable=True)
