from sqlalchemy import Column, BigInteger, Integer, String, Boolean, TIMESTAMP
from sqlalchemy.sql import func

from app.core.database import Base


class ServiceablePincode(Base):
    __tablename__ = "serviceable_pincodes"
    __table_args__ = {"schema": "master"}

    pincode_id = Column(BigInteger, primary_key=True, index=True)
    pincode = Column(Integer, unique=True, nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())