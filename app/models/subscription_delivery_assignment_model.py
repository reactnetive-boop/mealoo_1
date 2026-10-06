import uuid

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class SubscriptionDeliveryAssignment(Base):
    """
    History of which delivery partner serves a subscription.

    At most one row per subscription is 'active'; it mirrors
    subscriptions.delivery_boy_reference_id. Reassigning or unassigning ends
    the active row instead of overwriting it, so who delivered what, and who
    decided it, stays on record.
    """

    __tablename__ = "subscription_delivery_assignments"

    __table_args__ = (
        CheckConstraint("status IN ('active', 'ended')", name="chk_sub_assignment_status"),
        Index("idx_sub_assignments_subscription", "subscription_reference_id"),
        Index("idx_sub_assignments_delivery_boy", "delivery_boy_reference_id", "status"),
        Index(
            "uq_sub_assignment_active", "subscription_reference_id",
            unique=True, postgresql_where=text("status = 'active'"),
        ),
        {"schema": "subscription"},
    )

    assignment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    subscription_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.subscription_id", name="sub_assignments_subscription_id_fkey"),
        nullable=False,
    )

    delivery_boy_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("delivery.delivery_boys.delivery_boy_id", name="sub_assignments_delivery_boy_id_fkey"),
        nullable=False,
    )

    # active | ended
    status = Column(String(20), nullable=False, default="active", server_default="active")

    assigned_by = Column(UUID(as_uuid=True), nullable=True)

    # admin | system (carried over on a package switch)
    assigned_by_type = Column(String(20), nullable=False, default="admin", server_default="admin")

    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Open meals handed to the partner when the assignment was made
    orders_assigned = Column(Integer, nullable=False, default=0, server_default="0")

    note = Column(Text, nullable=True)

    ended_at = Column(DateTime(timezone=True), nullable=True)

    ended_by = Column(UUID(as_uuid=True), nullable=True)

    ended_by_type = Column(String(20), nullable=True)

    # reassigned | unassigned | partner_deactivated | partner_rejected |
    # partner_moved_kitchen |
    # subscription_switched
    end_reason = Column(String(50), nullable=True)
