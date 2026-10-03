import uuid

from sqlalchemy import Column, String, Boolean, DateTime, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID

from datetime import datetime, timezone

from app.core.database import Base


class UserOTPLog(Base):

    __tablename__ = "otp_logs"

    __table_args__ = {
        "schema": "auth"
    }

    otp_log_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    contact = Column(
        String(255),
        nullable=False,
        index=True
    )

    # 'sms' | 'email'
    channel = Column(
        String(10),
        nullable=False
    )

    # 'registration' | 'login' | 'phone_change' | 'email_change'
    purpose = Column(
        String(30),
        nullable=False
    )

    otp_hash = Column(
        Text,
        nullable=False
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

    verified_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    attempts = Column(
        SmallInteger,
        default=0
    )

    is_used = Column(
        Boolean,
        default=False
    )

    hashed_password = Column(
        Text,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
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
