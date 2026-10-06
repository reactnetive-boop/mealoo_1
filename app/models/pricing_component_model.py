import uuid

from sqlalchemy import Column, String, Boolean, Integer, Numeric, Text, DateTime, CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class PricingComponent(Base):
    """
    One version of one admin-configured pricing component.

    Rows are never edited: a change inserts a new version and stamps
    superseded_at on the old one, so the table is also the pricing history and
    audit trail. The current configuration is every row with superseded_at
    NULL.
    """

    __tablename__ = "pricing_components"

    __table_args__ = (
        CheckConstraint("value >= 0", name="chk_pricing_value_non_negative"),
        CheckConstraint("calc_type IN ('fixed', 'percentage')", name="chk_pricing_calc_type"),
        CheckConstraint("applies_to IN ('all', 'subscription', 'extra_order')", name="chk_pricing_applies_to"),
        CheckConstraint("charge_basis IN ('per_unit', 'per_delivery', 'per_order')", name="chk_pricing_basis"),
        Index(
            "uq_pricing_component_current",
            "component_key",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
        {"schema": "master"},
    )

    pricing_component_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # sms_charge | payment_gateway_charge | packaging_charge | delivery_charge
    # | platform_commission | delivery_partner_payout
    component_key = Column(String(50), nullable=False)

    label = Column(String(100), nullable=False)

    # fixed (rupees) | percentage (of the food amount)
    calc_type = Column(String(20), nullable=False)

    value = Column(Numeric(10, 2), nullable=False)

    # all | subscription | extra_order
    applies_to = Column(String(20), nullable=False, default="all")

    # For fixed amounts: per_unit (each meal x quantity), per_delivery (each
    # meal drop), per_order (once per checkout). Ignored for percentages.
    charge_basis = Column(String(20), nullable=False, default="per_order")

    # True: added to what the customer pays and shown in the breakdown.
    # False: an internal cost (e.g. the delivery partner payout).
    is_customer_facing = Column(Boolean, nullable=False, default=True)

    is_active = Column(Boolean, nullable=False, default=True)

    version = Column(Integer, nullable=False, default=1)

    effective_from = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    superseded_at = Column(DateTime(timezone=True), nullable=True)

    created_by = Column(UUID(as_uuid=True), nullable=True)

    change_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
