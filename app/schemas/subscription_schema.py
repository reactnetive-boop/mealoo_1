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
