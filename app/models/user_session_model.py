from sqlalchemy import (
    Column,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint
)

from sqlalchemy.dialects.postgresql import (
    UUID,
    JSONB,
    INET
)

from sqlalchemy.sql import func

import uuid

from app.core.database import Base


class UserSession(Base):

    __tablename__ = "user_sessions"

    __table_args__ = (
        UniqueConstraint(
            "refresh_token",
            name="user_sessions_refresh_token_key"
        ),
        {"schema": "auth"}
    )

    user_session_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    user_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "auth.users.user_id",
            name="fk_sessions_user"
        ),
        nullable=False
    )

    refresh_token = Column(
        Text,
        nullable=False
    )

    device_info = Column(JSONB)

    ip_address = Column(INET)

    last_active_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

    revoked_at = Column(
        DateTime(timezone=True)
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )