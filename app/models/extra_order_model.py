import uuid

from sqlalchemy import Column, String, Numeric, SmallInteger, Date, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class ExtraOrder(Base):

    __tablename__ = "extra_orders"

    __table_args__ = {
        "schema": "subscription"
    }

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    user_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True
    )

    vendor_id = Column(
        UUID(as_uuid=True),
        nullable=False
    )

    address_id = Column(
        UUID(as_uuid=True),
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

    total_price = Column(
        Numeric(10, 2),
        nullable=False
    )

    delivery_date = Column(
        Date,
        nullable=False
    )

    # 'breakfast' | 'lunch' | 'dinner'
    meal_slot = Column(
        String(20),
        nullable=False
    )

    # 'pending' | 'confirmed' | 'preparing' | 'out_for_delivery' | 'delivered' | 'cancelled'
    status = Column(
        String(30),
        nullable=False,
        default="pending"
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
