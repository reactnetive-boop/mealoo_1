import uuid

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class DeliveryPartnerVendor(Base):
    """
    Which kitchens a delivery partner serves (set by Orleeno).

    A partner may serve several kitchens; a kitchen has at most one current
    partner, so its new orders and subscription meals can be given to that
    partner automatically (app/domain/vendor_partner.py). Rows are ended,
    never overwritten, so the history of who covered a kitchen is kept.
    """

    __tablename__ = "delivery_partner_vendors"

    __table_args__ = (
        CheckConstraint("status IN ('active', 'ended')", name="chk_partner_vendor_status"),
        Index("idx_partner_vendors_partner", "delivery_boy_reference_id", "status"),
        Index("idx_partner_vendors_provider", "provider_reference_id"),
        Index(
            "uq_partner_vendor_active_kitchen", "provider_reference_id",
            unique=True, postgresql_where=text("status = 'active'"),
        ),
        {"schema": "delivery"},
    )

    assignment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    delivery_boy_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("delivery.delivery_boys.delivery_boy_id", name="partner_vendors_delivery_boy_id_fkey"),
        nullable=False,
    )

    provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="partner_vendors_provider_id_fkey"),
        nullable=False,
    )

    # active | ended
    status = Column(String(20), nullable=False, default="active", server_default="active")

    assigned_by = Column(UUID(as_uuid=True), nullable=True)

    # admin | system (migration)
    assigned_by_type = Column(String(20), nullable=False, default="admin", server_default="admin")

    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    note = Column(Text, nullable=True)

    ended_at = Column(DateTime(timezone=True), nullable=True)

    ended_by = Column(UUID(as_uuid=True), nullable=True)

    ended_by_type = Column(String(20), nullable=True)

    # removed | moved_to_other_partner | migration_duplicate_kitchen
    end_reason = Column(String(50), nullable=True)
