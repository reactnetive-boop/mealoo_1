import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    TIMESTAMP,
    BigInteger
)

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.sql import func

from app.core.database import Base


class ServiceUnavailableLog(Base):

    __tablename__ = (
        "service_unavailable_logs"
    )

    __table_args__ = {
        "schema": "master"
    }

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    log_id = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )

    provider_id = Column(
        UUID(as_uuid=True),
        nullable=True
    )

    pincode = Column(
        Integer,
        nullable=False
    )

    house_no = Column(
        String(100)
    )

    address = Column(
        Text
    )

    landmark = Column(
        String(255)
    )

    city = Column(
        String(100)
    )

    state = Column(
        String(100)
    )

    requested_from = Column(
        String(50)
    )

    remarks = Column(
        Text
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now()
    )