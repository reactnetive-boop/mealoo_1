import uuid

from sqlalchemy import Column, SmallInteger, Text, Boolean, Date, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class Review(Base):

    __tablename__ = "reviews"

    __table_args__ = {
        "schema": "provider"
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

    subscription_id = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    vendor_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True
    )

    order_id = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    package_id = Column(
        UUID(as_uuid=True),
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
