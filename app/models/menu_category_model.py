import uuid

from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    Text,
    TIMESTAMP
)

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.sql import func

from app.core.database import Base


class MenuCategory(Base):

    __tablename__ = "menu_categories"

    __table_args__ = {
        "schema": "master"
    }

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    category_id = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )

    category_name = Column(
        String(150),
        nullable=False
    )

    category_slug = Column(
        String(150),
        unique=True
    )

    description = Column(
        Text
    )

    display_order = Column(
        Integer,
        default=0
    )

    is_active = Column(
        Boolean,
        default=True
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )