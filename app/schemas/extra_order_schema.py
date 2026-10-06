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

    # The kitchen; all packages must be sold by it
    vendor_id: UUID

    address_id: UUID

    # Business-local date (YYYY-MM-DD, IST). Today only before the slot cut-off.
    delivery_date: date

    meal_slot: MealSlot

    items: List[OrderItemRequest] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="At least one package item required"
    )


class ExtraOrderResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    extra_order_id: UUID

    checkout_id: Optional[UUID] = None

    user_reference_id: UUID

    vendor_reference_id: UUID

    vendor_name: Optional[str] = None

    address_reference_id: UUID

    package_reference_id: UUID

    package_name: Optional[str] = None

    quantity: int

    # Selling price per unit of the package
    unit_price: Decimal

    charges_amount: Decimal = Decimal("0")

    # What the customer paid for this order (food + charges)
    total_price: Decimal

    price_breakdown: Optional[dict] = None

    delivery_date: date

    meal_slot: str

    status: str

    cancel_reason: Optional[str] = None

    refund_amount: Optional[Decimal] = None

    # Shown to the customer on the delivery day only; never to the kitchen
    otp_for_delivery: Optional[str] = None
    delivery_window: Optional[dict] = None

    can_cancel: bool = False

    delivered_at: Optional[datetime] = None

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

    page: int = 1

    limit: int = 100

    has_more: bool = False

    orders: List[ExtraOrderResponse]
