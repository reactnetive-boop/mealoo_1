from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    Text,
    ForeignKey
)

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.sql import func

from sqlalchemy.types import TIMESTAMP

import uuid

from app.core.database import Base

from sqlalchemy.orm import relationship

class MenuPackageImage(
    Base
):

    __tablename__ = "menu_package_images"

    __table_args__ = {
        "schema": "master"
    }

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    image_id = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True
    )

    package_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("master.menu_packages.package_id")
    )

    image_url = Column(
        Text,
        nullable=False
    )

    is_primary = Column(
        Boolean,
        default=False
    )

    display_order = Column(
        Integer,
        default=1
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now()
    )

    menu_package = relationship(
        "MenuPackage",
        back_populates="images"
    )