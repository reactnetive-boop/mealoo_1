import uuid

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func

from app.core.database import Base


class Complaint(Base):

    __tablename__ = "complaints"

    __table_args__ = (
        Index("idx_complaints_user", "user_reference_id"),
        Index("idx_complaints_vendor", "vendor_reference_id"),
        Index("idx_complaints_status", "status"),
        {"schema": "provider"},
    )

    complaint_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="complaints_user_id_fkey"),
        nullable=False,
        index=True
    )

    subscription_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.subscription_id", name="complaints_subscription_id_fkey"),
        nullable=True
    )

    vendor_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="complaints_vendor_id_fkey"),
        nullable=True
    )

    order_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.extra_orders.extra_order_id", name="complaints_order_id_fkey"),
        nullable=True
    )

    # 'vendor' | 'platform' | 'delivery' | 'package'
    against = Column(
        String(30),
        nullable=False
    )

    # 'open' | 'in_progress' | 'resolved' | 'closed' | 'rejected'
    status = Column(
        String(20),
        nullable=False,
        default="open"
    )

    subject = Column(
        String(255),
        nullable=False
    )

    description = Column(
        Text,
        nullable=False
    )

    evidence_urls = Column(
        ARRAY(Text),
        nullable=True,
        default=[]
    )

    admin_notes = Column(
        Text,
        nullable=True
    )

    resolved_by = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    resolution = Column(
        Text,
        nullable=True
    )

    resolved_at = Column(
        DateTime(timezone=True),
        nullable=True
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
