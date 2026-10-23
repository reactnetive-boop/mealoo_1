import uuid

from sqlalchemy import Column, SmallInteger, Text, Boolean, Date, DateTime, ForeignKey, CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class Review(Base):

    __tablename__ = "reviews"

    __table_args__ = (
        CheckConstraint(
            "vendor_rating >= 1 AND vendor_rating <= 5",
            name="chk_vendor_rating"
        ),
        CheckConstraint(
            "package_rating IS NULL OR (package_rating >= 1 AND package_rating <= 5)",
            name="chk_pkg_rating2"
        ),
        Index("idx_reviews_vendor", "vendor_reference_id"),
        Index("idx_reviews_pkg", "package_reference_id"),
        # one visible review per one-time order and per subscription meal
        Index(
            "uq_reviews_extra_order", "user_reference_id", "order_reference_id", unique=True,
            postgresql_where=text("order_reference_id IS NOT NULL AND is_visible"),
        ),
        Index(
            "uq_reviews_subscription_meal", "user_reference_id", "subscription_order_reference_id", unique=True,
            postgresql_where=text("subscription_order_reference_id IS NOT NULL AND is_visible"),
        ),
        # package listings aggregate ratings per (package, kitchen)
        Index(
            "idx_reviews_package_rating", "package_reference_id", "vendor_reference_id",
            postgresql_where=text("is_visible AND package_rating IS NOT NULL"),
        ),
        {"schema": "provider"},
    )

    review_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="reviews_user_id_fkey"),
        nullable=False,
        index=True
    )

    subscription_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.subscription_id", name="reviews_subscription_id_fkey"),
        nullable=True
    )

    vendor_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="reviews_vendor_id_fkey"),
        nullable=False,
        index=True
    )

    order_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.extra_orders.extra_order_id", name="reviews_order_id_fkey"),
        nullable=True
    )

    # A specific delivered meal of a subscription (subscription.orders)
    subscription_order_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.orders.order_id", name="reviews_subscription_order_id_fkey"),
        nullable=True,
    )

    package_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("master.menu_packages.package_id", name="reviews_package_id_fkey"),
        nullable=True
    )

    # 1–5
    vendor_rating = Column(
        SmallInteger,
        nullable=False
    )

    # 1–5
    package_rating = Column(
        SmallInteger,
        nullable=True
    )

    review_text = Column(
        Text,
        nullable=True
    )

    review_date = Column(
        Date,
        nullable=True
    )

    is_visible = Column(
        Boolean,
        default=True
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
