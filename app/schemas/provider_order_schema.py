from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


# ── Subscription Order ────────────────────────────────────

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
    otp_for_delivery: Optional[str]
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
    final_amount: Decimal
    free_skips_total: int
    free_skips_used: int
    notes: Optional[str]
    cancelled_at: Optional[datetime]
    cancel_reason: Optional[str]
    created_at: Optional[datetime]


class ProviderSubscriptionListResponse(BaseModel):

    success: bool
    total: int
    subscriptions: List[ProviderSubscriptionResponse]


class ProviderSubscriptionDetailResponse(BaseModel):

    success: bool
    subscription: ProviderSubscriptionResponse
    orders: List[SubscriptionOrderResponse]


# ── Subscription Orders ───────────────────────────────────

class SubscriptionOrderListResponse(BaseModel):

    success: bool
    total: int
    orders: List[SubscriptionOrderResponse]


class UpdateOrderStatusRequest(BaseModel):

    status: str


class UpdateOrderStatusResponse(BaseModel):

    success: bool
    message: str
    order_id: UUID
    status: str


# ── Extra Orders ──────────────────────────────────────────

class ProviderExtraOrderResponse(BaseModel):

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


class ProviderExtraOrderListResponse(BaseModel):

    success: bool
    total: int
    orders: List[ProviderExtraOrderResponse]


# ── Daily Food Calculator ─────────────────────────────────

class FoodSummaryItemResponse(BaseModel):

    item_name: str
    quantity_per_serving: str
    total_servings: int


class DailyFoodSummaryResponse(BaseModel):

    success: bool
    date: date
    meal_slot: str
    subscription_orders_count: int
    extra_orders_count: int
    total_orders_count: int
    items: List[FoodSummaryItemResponse]
