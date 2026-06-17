from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import DateTime
from sqlalchemy import Boolean
from sqlalchemy.sql import func

from app.core.database import Base
from sqlalchemy.dialects.postgresql import UUID
import uuid

class OTPLog(Base):

    __tablename__ = "otp_logs"

    __table_args__ = {
            "schema": "provider"
    }

    otp_log_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    mobile_number = Column(
        String,
        nullable=False,
        index=True
    )

    otp = Column(
        String,
        nullable=False
    )

    is_verified = Column(
        Boolean,
        default=False
    )

    attempts = Column(
        Integer,
        nullable=True
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    hashed_password = Column(
        String,
        nullable=False
    )
