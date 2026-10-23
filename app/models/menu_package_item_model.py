import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
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

    # Display label, e.g. "400 g", "4 pcs", "1 bowl (300 g)". Built from the
    # fields below when a unit is given (app/domain/item_quantity.py); free
    # text from older app versions otherwise.
    quantity = Column(
        String(100)
    )

    # Amount in `quantity_unit`: g | kg | pcs | bowl | ml | l
    quantity_value = Column(
        Numeric(10, 2),
        nullable=True
    )

    quantity_unit = Column(
        String(10),
        nullable=True
    )

    # What one bowl holds (bowls only), in `bowl_capacity_unit`: g | ml
    bowl_capacity = Column(
        Numeric(10, 2),
        nullable=True
    )

    bowl_capacity_unit = Column(
        String(5),
        nullable=True
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