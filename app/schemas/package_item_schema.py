from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from typing import Optional

from uuid import UUID

from app.domain import item_quantity


class ItemQuantityFields(BaseModel):
    """
    How much of an item the package contains. Send `quantity_value` with a
    `quantity_unit` (g, kg, pcs, bowl, ml, l); for bowls optionally
    `bowl_capacity` + `bowl_capacity_unit` (g or ml). The server builds the
    display label ("400 g", "4 pcs", "1 bowl (300 g)") into `quantity`.
    Without a unit, `quantity` is stored as free text (older app versions).
    """

    quantity: Optional[str] = Field(None, max_length=100, description="Free-text quantity; ignored when quantity_unit is given")
    quantity_value: Optional[Decimal] = Field(None, description="Amount in quantity_unit, e.g. 400")
    quantity_unit: Optional[str] = Field(None, max_length=10, description="g | kg | pcs | bowl | ml | l")
    bowl_capacity: Optional[Decimal] = Field(None, description="What one bowl holds (quantity_unit = bowl)")
    bowl_capacity_unit: Optional[str] = Field(None, max_length=5, description="g | ml")

    @model_validator(mode="after")
    def _check_quantity(self):
        item_quantity.normalize(**{f: getattr(self, f) for f in item_quantity.FIELDS})
        return self


class AddPackageItemRequest(ItemQuantityFields):

    package_id: UUID
    item_name: str = Field(..., min_length=1, max_length=255)
    item_order: Optional[int] = Field(None, ge=0, le=1000)


class UpdatePackageItemRequest(ItemQuantityFields):

    item_name: Optional[str] = Field(None, min_length=1, max_length=255)
    item_order: Optional[int] = Field(None, ge=0, le=1000)


class PackageItemResponse(BaseModel):

    success: bool
    message: str
    item_id: UUID | None = None


class CommonResponse(BaseModel):

    success: bool
    message: str