from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field
from enum import Enum


class SubscriptionType(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    HALF_YEARLY = "half_yearly"
    YEARLY = "yearly"


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

    duration_days: int

    free_skips: int

    discount_percent: Decimal


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
        description="Quantity per package (1-5)"
    )


class CreateSubscriptionRequest(BaseModel):

    vendor_id: UUID

    plan_id: UUID

    address_id: UUID

    start_date: date

    items: List[SubscriptionItemRequest] = Field(
        ...,
        min_length=1
    )


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

    plan_reference_id: UUID

    user_address_reference_id: UUID

    status: str

    meal_slot: str

    subscription_type: str

    start_date: date

    end_date: date

    free_skips_total: int

    free_skips_used: int

    total_amount: Decimal

    discount_amount: Decimal

    final_amount: Decimal

    pause_start_date: Optional[date]

    total_days_paused: int

    notes: Optional[str]

    cancelled_at: Optional[datetime]

    cancel_reason: Optional[str]

    created_at: Optional[datetime]

    packages: List[SubscriptionPackageResponse] = []


class CreateSubscriptionResponse(BaseModel):

    success: bool

    message: str

    subscription_id: UUID

    total_amount: Decimal

    discount_amount: Decimal

    final_amount: Decimal

    wallet_balance_after: Decimal


class SubscriptionListResponse(BaseModel):

    success: bool

    total: int

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


# ── Package Switch ───────────────────────────────────────

class PackageSwitchRequest(BaseModel):

    new_package_id: UUID

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
