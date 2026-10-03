from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import DateTime
from sqlalchemy import Boolean
from sqlalchemy import Text
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
        nullable=False,
        default=0,
        server_default="0"
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

    # 'registration' | 'password_reset' — an OTP issued for one flow
    # must never be usable to complete the other
    purpose = Column(
        String(30),
        nullable=False,
        server_default="registration",
        default="registration"
    )

    # Password reset: verifying a reset OTP issues a one-time token (stored
    # hashed) that the final reset call must present.
    reset_token_hash = Column(
        Text,
        nullable=True
    )

    reset_token_expires_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
