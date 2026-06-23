import uuid

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class DeliveryBoyOTPLog(Base):

    __tablename__ = "delivery_boy_otp_logs"

    __table_args__ = {"schema": "delivery"}

    delivery_boy_otp_log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    mobile_number = Column(String(15), nullable=False, index=True)

    otp = Column(String(6), nullable=False)

    hashed_password = Column(String, nullable=False)

    is_verified = Column(Boolean, default=False)

    attempts = Column(Integer, default=0)

    expires_at = Column(DateTime(timezone=True), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
