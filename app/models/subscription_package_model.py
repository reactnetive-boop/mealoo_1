import uuid

from sqlalchemy import Column, SmallInteger, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.core.database import Base


class SubscriptionPackage(Base):

    __tablename__ = "subscription_packages"

    __table_args__ = {
        "schema": "subscription"
    }

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.id"),
        nullable=False
    )

    package_id = Column(
        UUID(as_uuid=True),
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
