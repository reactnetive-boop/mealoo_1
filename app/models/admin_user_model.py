import uuid

from sqlalchemy import BigInteger, Column, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID, CITEXT
from sqlalchemy.sql import func

from app.core.crypto import EncryptedString
from app.core.database import Base
from app.models.mixins import AccountSecurityMixin


class AdminUser(AccountSecurityMixin, Base):

    __tablename__ = "admin_users"

    __table_args__ = (
        UniqueConstraint("email", name="admin_users_email_key"),
        {"schema": "master"},
    )

    admin_user_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    full_name = Column(
        String(100),
        nullable=True
    )

    email = Column(
        CITEXT,
        nullable=False
    )

    password_hash = Column(
        Text,
        nullable=False
    )

    role = Column(
        String(50),
        nullable=True
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False
    )

    last_login_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Two-factor login (app.core.totp). The secret is encrypted at rest; it is
    # set at enrolment and only counts once a code from it has been confirmed.
    totp_secret = Column(EncryptedString, nullable=True)
    totp_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    totp_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    # last accepted time step: a code can never be used twice
    totp_last_step = Column(BigInteger, nullable=True)
    # sha256 hashes of unused one-time recovery codes
    totp_recovery_hashes = Column(JSONB, nullable=True)
