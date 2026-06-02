import uuid

from sqlalchemy import Column
from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy import DateTime

from sqlalchemy.dialects.postgresql import UUID

from datetime import datetime
from datetime import timezone

from app.core.database import Base


class ProviderSelectedPackage(Base):

    __tablename__ = "provider_selected_packages"
    __table_args__ = {"schema": "provider"}

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    selection_id = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )

    provider_id = Column(
        UUID(as_uuid=True),
        nullable=False
    )

    package_id = Column(
        UUID(as_uuid=True),
        nullable=False
    )

    is_active = Column(
        Boolean,
        default=True
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )