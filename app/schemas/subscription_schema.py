from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ── Plan Options ─────────────────────────────────────────

class SubscriptionPlanOptionsResponse(BaseModel):

    meal_slots: List[str]

    subscription_types: List[str]


# ── Plans ────────────────────────────────────────────────

class SubscriptionPlanResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    subscription_plan_id: UUID

    subscription_type: str

    meal_slot: str

    # The individual daily meals of the plan, e.g. ["lunch", "dinner"]
    meal_slots: List[str] = []

    duration_days: int

    # Custom plans: the customer picks the end date within these bounds
    is_custom: bool = False

    custom_min_days: Optional[int] = None

    custom_max_days: Optional[int] = None

    free_skips: int

    discount_percent: Decimal

    earliest_start_date: Optional[date] = None


class SubscriptionPlanListResponse(BaseModel):

    success: bool

    total: int

    plans: List[SubscriptionPlanResponse]


# ── Subscribe request ────────────────────────────────────

class SubscriptionItemRequest(BaseModel):

    package_id: UUID

    quantity: int = Field(
        ...,
        ge=1,
        le=5,
        description="Quantity per meal (1-5)"
    )


class CreateSubscriptionRequest(BaseModel):

    vendor_id: UUID

    plan_id: UUID

    address_id: UUID

    start_date: date

    # Custom plans only: last meal date (inclusive)
    end_date: Optional[date] = None

    # One package per subscription (the cart holds one tiffin)
    items: List[SubscriptionItemRequest] = Field(
        ...,
        min_length=1,
        max_length=1
    )


class SubscriptionQuoteRequest(BaseModel):

    vendor_id: UUID

    package_id: UUID

    plan_id: UUID

    quantity: int = Field(1, ge=1, le=5)

    address_id: Optional[UUID] = None

    start_date: Optional[date] = None

    end_date: Optional[date] = None


# ── Subscription responses ───────────────────────────────

class SubscriptionPackageResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    subscription_package_id: UUID

    package_reference_id: UUID

    quantity: int

    unit_price: Decimal


class SubscriptionResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    subscription_id: UUID

    user_reference_id: UUID

    vendor_reference_id: UUID

    vendor_name: Optional[str] = None

    plan_reference_id: UUID

    user_address_reference_id: UUID

    address_line: Optional[str] = None

    status: str

    meal_slot: str

    subscription_type: str

    start_date: date

    # Exclusive: the last meal is on last_meal_date
    end_date: date

    last_meal_date: Optional[date] = None

    free_skips_total: int

    free_skips_used: int

    total_amount: Decimal

    discount_amount: Decimal

    charges_amount: Decimal = Decimal("0")

    final_amount: Decimal

    refunded_amount: Decimal = Decimal("0")

    meal_value: Optional[Decimal] = None

    pause_start_date: Optional[date]

    total_days_paused: int

    notes: Optional[str]

    cancelled_at: Optional[datetime]

    cancel_reason: Optional[str]

    created_at: Optional[datetime]

    package_id: Optional[UUID] = None

    package_name: Optional[str] = None

    quantity: Optional[int] = None

    unit_price: Optional[Decimal] = None

    price_breakdown: Optional[dict] = None

    next_meal: Optional[dict] = None

    can_pause: bool = False

    can_resume: bool = False

    can_cancel: bool = False

    can_switch: bool = False

    packages: List[SubscriptionPackageResponse] = []


class CreateSubscriptionResponse(BaseModel):

    success: bool

    message: str

    subscription_id: UUID

    start_date: Optional[date] = None

    end_date: Optional[date] = None

    total_amount: Decimal

    discount_amount: Decimal

    charges_amount: Decimal = Decimal("0")

    final_amount: Decimal

    wallet_balance_after: Decimal

    price_breakdown: Optional[dict] = None


class SubscriptionListResponse(BaseModel):

    success: bool

    total: int

    page: int = 1

    limit: int = 100

    has_more: bool = False

    subscriptions: List[SubscriptionResponse]


class CancelSubscriptionRequest(BaseModel):

    cancel_reason: Optional[str] = Field(
        None,
        max_length=500
    )


class PauseSubscriptionResponse(BaseModel):

    success: bool

    message: str

    pause_start_date: str


class ResumeSubscriptionResponse(BaseModel):

    success: bool

    message: str

    resume_date: str

    new_end_date: str

    days_paused: int

    new_orders_created: int


# ── Subscription Orders (customer view) ──────────────────

class UserSubscriptionOrderResponse(BaseModel):
    """One daily meal belonging to a subscription."""

    model_config = ConfigDict(from_attributes=True)

    order_id: UUID

    subscription_reference_id: UUID

    vendor_reference_id: UUID

    delivery_address_reference_id: UUID

    delivery_boy_reference_id: Optional[UUID]

    order_date: date

    meal_slot: str

    # scheduled | preparing | ready_for_pickup | picked_up | out_for_delivery |
    # delivered | skipped | cancelled
    status: str

    is_free_skip: bool

    skip_requested_at: Optional[datetime]

    # Same-day cut-off for this meal (free skip / cancellation window)
    skip_deadline: Optional[datetime]

    delivered_at: Optional[datetime]

    delivery_notes: Optional[str]

    cancel_reason: Optional[str] = None

    refund_amount: Optional[Decimal] = None

    # The code the customer gives the delivery partner. Only returned on the
    # day of the meal until it is delivered, and never to the kitchen or partner.
    otp_for_delivery: Optional[str]

    picked_up_at: Optional[datetime] = None

    out_for_delivery_at: Optional[datetime] = None

    can_skip: bool = False
    delivery_window: Optional[dict] = None

    skip_will_refund: bool = False

    created_at: Optional[datetime]

    updated_at: Optional[datetime]


class UserSubscriptionOrderListResponse(BaseModel):

    success: bool

    subscription_id: UUID

    subscription_status: str

    total: int

    # Count of orders per status, e.g. {"scheduled": 5, "delivered": 2}
    status_summary: dict

    orders: List[UserSubscriptionOrderResponse]


class UserOrderAddressInfo(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    user_address_id: UUID

    label: Optional[str]

    address_line1: str

    address_line2: Optional[str]

    landmark: Optional[str]

    city: str

    state: str

    pin_code: str

    latitude: Optional[Decimal]

    longitude: Optional[Decimal]


class UserOrderPackageInfo(BaseModel):

    package_id: UUID

    package_name: str

    meal_type: Optional[str]

    food_type: Optional[str]

    quantity: int

    unit_price: Decimal

    primary_image: Optional[str]


class UserOrderVendorInfo(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    provider_id: UUID

    business_name: Optional[str]

    mobile_number: Optional[str]

    area: Optional[str]

    city: Optional[str]

    profile_image: Optional[str]


class UserOrderDeliveryBoyInfo(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    delivery_boy_id: UUID

    full_name: Optional[str]

    mobile_number: Optional[str]

    vehicle_type: Optional[str]

    vehicle_number: Optional[str]

    profile_image: Optional[str]


class UserSubscriptionOrderDetailResponse(BaseModel):

    success: bool

    order: UserSubscriptionOrderResponse

    delivery_address: UserOrderAddressInfo

    packages: List[UserOrderPackageInfo]

    vendor: Optional[UserOrderVendorInfo] = None

    # None until the provider assigns a delivery partner
    delivery_boy: Optional[UserOrderDeliveryBoyInfo] = None


class SkipOrderResponse(BaseModel):

    success: bool

    message: str

    order_id: UUID

    status: str

    # True when a free skip was consumed and the meal amount refunded
    is_free_skip: bool

    # Why the skip was not free: 'cutoff_passed' | 'no_free_skips_left' | None
    not_free_reason: Optional[str]

    # Same-day cutoff for this order's meal slot (breakfast 06:00, lunch 09:00, dinner 15:00)
    skip_deadline: datetime

    refund_amount: Decimal

    wallet_balance_after: Optional[Decimal]

    free_skips_total: int

    free_skips_used: int

    free_skips_remaining: int


# ── Package Switch ───────────────────────────────────────

class PackageSwitchRequest(BaseModel):

    new_package_id: UUID

    # The kitchen selling the new package (required for Orleeno catalogue
    # packages; defaults to the package's own kitchen otherwise)
    new_provider_id: Optional[UUID] = None

    # Required only when the subscription holds more than one package
    old_package_id: Optional[UUID] = None


class PackageSwitchCalculation(BaseModel):
    """Unused Service Value Method breakdown (Package Switch Policy §4/§16)."""

    switch_request_date: date

    effective_date: date

    total_days: int

    used_days: int

    remaining_days: int

    old_daily_cost: Decimal

    new_daily_cost: Decimal

    remaining_value: Decimal

    new_remaining_cost: Decimal

    # new_remaining_cost - remaining_value (signed, before floor rule)
    adjustment_amount: Decimal

    # Floored to whole rupees (policy §17): what the customer pays now
    payment_amount: Decimal

    # Floored to whole rupees (policy §17): what is credited to the wallet
    wallet_credit_amount: Decimal

    # 'payment_required' | 'wallet_credit' | 'no_adjustment'
    action: str


class PackageSwitchPreviewResponse(BaseModel):

    success: bool

    old_package_id: UUID

    old_package_name: str

    old_provider_id: UUID

    new_package_id: UUID

    new_package_name: str

    new_provider_id: UUID

    calculation: PackageSwitchCalculation

    wallet_balance: Decimal


class PackageSwitchResponse(BaseModel):

    success: bool

    message: str

    switch_id: UUID

    old_subscription_id: UUID

    new_subscription_id: UUID

    new_provider_id: UUID

    effective_date: date

    payment_amount: Decimal

    wallet_credit_amount: Decimal

    wallet_balance_after: Decimal

    new_orders_created: int
