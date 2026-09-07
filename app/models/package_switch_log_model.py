import uuid

from sqlalchemy import (
    Column, String, Integer, Numeric, Date, DateTime, ForeignKey, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class PackageSwitchLog(Base):
    """Audit record for every package switch (Mealoo Package Switch Policy §14)."""

    __tablename__ = "package_switch_logs"

    __table_args__ = (
        Index("idx_package_switch_logs_user", "user_reference_id"),
        Index("idx_package_switch_logs_old_sub", "old_subscription_reference_id"),
        {"schema": "subscription"},
    )

    package_switch_log_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="package_switch_logs_user_id_fkey"),
        nullable=False
    )

    old_subscription_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.subscription_id", name="package_switch_logs_old_sub_fkey"),
        nullable=False
    )

    # Null until the switch completes successfully
    new_subscription_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.subscription_id", name="package_switch_logs_new_sub_fkey"),
        nullable=True
    )

    old_provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="package_switch_logs_old_provider_fkey"),
        nullable=False
    )

    new_provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="package_switch_logs_new_provider_fkey"),
        nullable=False
    )

    old_package_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("master.menu_packages.package_id", name="package_switch_logs_old_package_fkey"),
        nullable=False
    )

    new_package_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("master.menu_packages.package_id", name="package_switch_logs_new_package_fkey"),
        nullable=False
    )

    switch_request_date = Column(Date, nullable=False)

    effective_date = Column(Date, nullable=False)

    total_days = Column(Integer, nullable=False)

    used_days = Column(Integer, nullable=False)

    remaining_days = Column(Integer, nullable=False)

    old_daily_cost = Column(Numeric(10, 2), nullable=False)

    new_daily_cost = Column(Numeric(10, 2), nullable=False)

    remaining_value = Column(Numeric(10, 2), nullable=False)

    new_remaining_cost = Column(Numeric(10, 2), nullable=False)

    # new_remaining_cost - remaining_value (signed, before floor rule)
    adjustment_amount = Column(Numeric(10, 2), nullable=False)

    # Floored amounts actually moved (policy §17: truncate to whole rupee)
    payment_amount = Column(Numeric(10, 2), nullable=False, default=0)

    wallet_credit_amount = Column(Numeric(10, 2), nullable=False, default=0)

    # 'paid' | 'credited' | 'not_required'
    payment_status = Column(String(20), nullable=False)

    # 'completed' | 'failed'
    switch_status = Column(String(20), nullable=False, default="completed")

    created_by = Column(String(50), nullable=False, default="user")

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
