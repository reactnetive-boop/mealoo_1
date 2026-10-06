import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class DeliveryBoyLeave(Base):
    """A day a delivery partner does not work: their deliveries that day go to someone else."""

    __tablename__ = "delivery_boy_leaves"
    __table_args__ = (
        UniqueConstraint("delivery_boy_reference_id", "leave_date", name="uq_delivery_boy_leave_day"),
        {"schema": "delivery"},
    )

    delivery_boy_leave_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    delivery_boy_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("delivery.delivery_boys.delivery_boy_id", name="delivery_boy_leaves_delivery_boy_id_fkey"),
        nullable=False,
        index=True,
    )

    leave_date = Column(Date, nullable=False, index=True)

    reason = Column(String(255), nullable=True)

    # 'delivery_boy' or 'admin'
    created_by_type = Column(String(20), nullable=False, default="delivery_boy")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
