import uuid

from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Text, Date,
    ForeignKey, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func


from app.core.database import Base
from app.models.mixins import AccountSecurityMixin


class User(AccountSecurityMixin, Base):

    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR phone IS NOT NULL",
            name="chk_users_contact"
        ),
        UniqueConstraint("phone", name="users_phone_key"),
        UniqueConstraint("user_id", name="users_user_id_key"),
        Index("idx_users_email", "email"),
        Index("idx_users_phone", "phone"),
        Index("idx_users_status", "status"),
        {"schema": "auth"},
    )

    # Internal DB primary key
    id = Column(
        BigInteger,
        primary_key=True,
        index=True
    )

    # Public UUID
    user_id = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False,
        index=True
    )

    email = Column(
        String,
        unique=True,
        nullable=True
    )

    phone = Column(
        String(15),
        unique=True,
        nullable=True,
        index=True
    )

    phone_verified = Column(
        Boolean,
        default=False
    )

    email_verified = Column(
        Boolean,
        default=False
    )

    # Nullable — users registered via OTP-only have no password
    password_hash = Column(
        Text,
        nullable=True
    )

    full_name = Column(
        String(100),
        nullable=True
    )

    # 'male' | 'female' | 'other' | 'prefer_not_to_say'
    gender = Column(
        String(20),
        nullable=True
    )

    date_of_birth = Column(
        Date,
        nullable=True
    )

    avatar_url = Column(
        Text,
        nullable=True
    )

    is_profile_completed = Column(
        Boolean,
        default=False
    )

    # 'active' | 'inactive' | 'suspended' | 'deleted'
    status = Column(
        String(20),
        default="active"
    )

    referral_code = Column(
        String(12),
        unique=True,
        nullable=True
    )

    referred_by = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.user_id", name="fk_referred_by"),
        nullable=True
    )

    last_login_at = Column(
        DateTime(timezone=True),
        nullable=True
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

    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
