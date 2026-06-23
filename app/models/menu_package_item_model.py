import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    ForeignKey,
    TIMESTAMP
)

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.sql import func

from app.core.database import Base

from sqlalchemy.orm import relationship

class MenuPackageItem(Base):

    __tablename__ = "menu_package_items"

    __table_args__ = {
        "schema": "master"
    }

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    item_id = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )

    package_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "master.menu_packages.package_id"
        ),
        nullable=False
    )

    item_name = Column(
        String(255),
        nullable=False
    )

    quantity = Column(
        String(100)
    )

    item_order = Column(
        Integer,
        default=0
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now()
    )

    menu_package = relationship(
        "MenuPackage",
        back_populates="items"
    )