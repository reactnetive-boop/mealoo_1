from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field
from enum import Enum


class MealSlot(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"


class OrderItemRequest(BaseModel):

    package_id: UUID

    quantity: int = Field(
        ...,
        ge=1,
        le=5,
        description="Quantity per package (1-5)"
    )


class PlaceExtraOrderRequest(BaseModel):

    vendor_id: UUID

    address_id: UUID

    delivery_date: date

    meal_slot: MealSlot

    items: List[OrderItemRequest] = Field(
        ...,
        min_length=1,
        description="At least one package item required"
    )


class ExtraOrderResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    extra_order_id: UUID

    user_reference_id: UUID

    vendor_reference_id: UUID

    address_reference_id: UUID

    package_reference_id: UUID

    quantity: int

    unit_price: Decimal

    total_price: Decimal

    delivery_date: date

    meal_slot: str

    status: str

    created_at: Optional[datetime]


class PlaceOrderResponse(BaseModel):

    success: bool

    message: str

    total_amount: Decimal

    wallet_balance_after: Decimal

    orders: List[ExtraOrderResponse]


class ExtraOrderListResponse(BaseModel):

    success: bool

    total: int

    orders: List[ExtraOrderResponse]
