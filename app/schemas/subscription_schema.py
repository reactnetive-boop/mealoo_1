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


# ── Plans ────────────────────────────────────────────────

class SubscriptionPlanResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID

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

    id: UUID

    package_id: UUID

    quantity: int

    unit_price: Decimal


class SubscriptionResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    user_id: UUID

    vendor_id: UUID

    plan_id: UUID

    user_address_id: UUID

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
