from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


class AddToCartRequest(BaseModel):

    package_id: UUID

    # Kitchen selling the package (from the menu listing); required for
    # Orleeno catalogue packages
    provider_id: Optional[UUID] = None

    quantity: int = Field(
        ...,
        ge=1,
        le=10,
        description="Quantity (1–10)",
    )


class UpdateCartItemRequest(BaseModel):

    quantity: int = Field(
        ...,
        ge=1,
        le=10,
        description="Updated quantity (1–10)",
    )


class CartItemResponse(BaseModel):

    cart_item_id: UUID
    package_reference_id: UUID
    vendor_reference_id: UUID
    quantity: int
    package_name: str
    price: Decimal
    discounted_price: Optional[Decimal]
    effective_price: Decimal
    subscription_unit_price: Optional[Decimal] = None
    item_total: Decimal
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class CartResponse(BaseModel):

    success: bool
    total_items: int
    cart_total: Decimal
    items: List[CartItemResponse]


class AddToCartResponse(BaseModel):

    success: bool
    message: str
    cart_item: CartItemResponse


class RemoveFromCartResponse(BaseModel):

    success: bool
    message: str


class ClearCartResponse(BaseModel):

    success: bool
    message: str
