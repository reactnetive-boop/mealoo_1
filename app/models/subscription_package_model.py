import uuid

from sqlalchemy import Column, SmallInteger, Numeric, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.core.database import Base


class SubscriptionPackage(Base):

    __tablename__ = "subscription_packages"

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_sub_pkg_qty"),
        Index("idx_sub_packages_subscription", "subscription_reference_id"),
        {"schema": "subscription"},
    )

    subscription_package_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    subscription_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.subscription_id"),
        nullable=False
    )

    package_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("master.menu_packages.package_id", name="subscription_packages_package_id_fkey"),
        nullable=False
    )

    quantity = Column(
        SmallInteger,
        nullable=False,
        default=1
    )

    unit_price = Column(
        Numeric(10, 2),
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    subscription = relationship(
        "Subscription",
        back_populates="packages"
    )
