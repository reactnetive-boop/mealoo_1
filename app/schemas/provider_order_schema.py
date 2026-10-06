from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import date, date as Date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ── Subscription meal (kitchen view: never carries the customer's code) ──

class OrderPackageLine(BaseModel):
    package_id: UUID
    package_name: str
    quantity: int


class SubscriptionOrderResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    order_id: UUID
    subscription_reference_id: UUID
    user_reference_id: UUID
    vendor_reference_id: UUID
    delivery_address_reference_id: UUID
    order_date: date
    meal_slot: str
    status: str
    is_free_skip: bool
    delivered_at: Optional[datetime]
    delivery_notes: Optional[str]
    cancel_reason: Optional[str] = None
    picked_up_at: Optional[datetime] = None
    # Too many wrong pickup codes on this order; Orleeno support unlocks it
    pickup_locked: bool = False
    delivery_boy_reference_id: Optional[UUID] = None
    delivery_boy_name: Optional[str] = None
    customer_name: Optional[str] = None
    delivery_area: Optional[str] = None
    packages: List[OrderPackageLine] = []
    # Status changes this kitchen may make next
    next_actions: List[str] = []
    created_at: Optional[datetime]


# ── Subscription ──────────────────────────────────────────

class ProviderSubscriptionResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    subscription_id: UUID
    user_reference_id: UUID
    vendor_reference_id: UUID
    plan_reference_id: UUID
    user_address_reference_id: UUID
    status: str
    meal_slot: str
    subscription_type: str
    start_date: date
    end_date: date
    total_amount: Decimal
    discount_amount: Decimal
    charges_amount: Decimal = Decimal("0")
    final_amount: Decimal
    free_skips_total: int
    free_skips_used: int
    notes: Optional[str]
    cancelled_at: Optional[datetime]
    cancel_reason: Optional[str]
    created_at: Optional[datetime]
    # names for the kitchen (first name only; no phone or full address)
    customer_name: Optional[str] = None
    delivery_area: Optional[str] = None
    delivery_boy_reference_id: Optional[UUID] = None
    delivery_boy_name: Optional[str] = None
    packages: List[OrderPackageLine] = []


class ProviderSubscriptionListResponse(BaseModel):
    success: bool
    total: int
    subscriptions: List[ProviderSubscriptionResponse]


class ProviderSubscriptionDetailResponse(BaseModel):
    success: bool
    subscription: ProviderSubscriptionResponse
    orders: List[SubscriptionOrderResponse]


class SubscriptionOrderListResponse(BaseModel):
    success: bool
    date: Optional[Date] = None
    total: int
    page: int = 1
    has_more: bool = False
    orders: List[SubscriptionOrderResponse]


class UpdateOrderStatusRequest(BaseModel):
    status: str = Field(..., max_length=30)


class UpdateOrderStatusResponse(BaseModel):
    success: bool
    message: str
    order_id: UUID
    status: str


# ── One-time orders ───────────────────────────────────────

class ProviderExtraOrderResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    extra_order_id: UUID
    user_reference_id: UUID
    vendor_reference_id: UUID
    address_reference_id: UUID
    package_reference_id: UUID
    package_name: Optional[str] = None
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    delivery_date: date
    meal_slot: str
    status: str
    cancel_reason: Optional[str] = None
    picked_up_at: Optional[datetime] = None
    pickup_locked: bool = False
    delivery_boy_reference_id: Optional[UUID] = None
    delivery_boy_name: Optional[str] = None
    customer_name: Optional[str] = None
    delivery_area: Optional[str] = None
    next_actions: List[str] = []
    created_at: Optional[datetime]


class ProviderExtraOrderListResponse(BaseModel):
    success: bool
    total: int
    orders: List[ProviderExtraOrderResponse]


# ── Daily Food Calculator ─────────────────────────────────

class FoodSummaryItemResponse(BaseModel):
    item_name: str
    quantity_per_serving: str
    total_servings: int


class FoodSummaryPackageResponse(BaseModel):
    package_id: UUID
    package_name: Optional[str]
    meals: int


class DailyFoodSummaryResponse(BaseModel):
    success: bool
    date: Date
    meal_slot: str
    subscription_orders_count: int
    extra_orders_count: int
    total_orders_count: int
    packages: List[FoodSummaryPackageResponse] = []
    items: List[FoodSummaryItemResponse]
