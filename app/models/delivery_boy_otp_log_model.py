import uuid

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class DeliveryBoyOTPLog(Base):

    __tablename__ = "delivery_boy_otp_logs"

    __table_args__ = {"schema": "delivery"}

    delivery_boy_otp_log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    mobile_number = Column(String(15), nullable=False, index=True)

    # Keyed hash of the code, never the code itself
    otp = Column(Text, nullable=False)

    # Only set for registration OTPs (the password chosen at sign-up)
    hashed_password = Column(String, nullable=False)

    # 'registration' | 'password_reset'
    purpose = Column(String(30), nullable=False, default="registration", server_default="registration")

    is_verified = Column(Boolean, default=False)

    attempts = Column(Integer, nullable=False, default=0, server_default="0")

    expires_at = Column(DateTime(timezone=True), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    reset_token_hash = Column(Text, nullable=True)

    reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)
