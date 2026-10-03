import uuid

from sqlalchemy import (
    Column, BigInteger, String, Boolean, Text, Date, DateTime, ForeignKey,
    UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.mixins import AccountSecurityMixin


class DeliveryBoy(AccountSecurityMixin, Base):

    __tablename__ = "delivery_boys"

    __table_args__ = (
        UniqueConstraint("mobile_number", name="delivery_boys_mobile_number_key"),
        UniqueConstraint("delivery_boy_id", name="delivery_boys_delivery_boy_id_key"),
        Index("idx_delivery_boys_mobile", "mobile_number"),
        Index("idx_delivery_boys_provider", "assigned_provider_reference_id"),
        {"schema": "delivery"},
    )

    id = Column(BigInteger, primary_key=True, index=True)

    delivery_boy_id = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False,
        index=True
    )

    mobile_number = Column(String(15), nullable=False, unique=True, index=True)

    hashed_password = Column(String, nullable=False)

    full_name = Column(String(128), nullable=True)

    email = Column(String(255), nullable=True)

    date_of_birth = Column(Date, nullable=True)

    # male | female | other
    gender = Column(String(10), nullable=True)

    is_mobile_verified = Column(Boolean, default=False)

    is_active = Column(Boolean, default=True)

    # Duty status toggled from the app's home screen ("online" = accepting work)
    is_online = Column(Boolean, default=True, nullable=False, server_default='true')

    # bike | cycle | scooter | car
    vehicle_type = Column(String(30), nullable=True)

    vehicle_number = Column(String(20), nullable=True)

    profile_image = Column(Text, nullable=True)

    # nullable — delivery boys may be platform-wide or tied to one provider
    assigned_provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "provider.providers.provider_id",
            name="delivery_boys_assigned_provider_id_fkey"
        ),
        nullable=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Admin review after documents are verified: pending | approved | rejected.
    # Only approved, active partners can be assigned deliveries.
    approval_status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending"
    )
    approval_note = Column(Text, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(UUID(as_uuid=True), nullable=True)
