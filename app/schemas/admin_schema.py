from typing import List, Optional, Any, Union, Literal
from uuid import UUID
from decimal import Decimal
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.meal_type import normalize_meal_type, normalize_food_type
from app.schemas.menu_schema import _zero_is_none


# ── Auth ──────────────────────────────────────────────────

class AdminLoginRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., max_length=128)


class AdminLoginResponse(BaseModel):
    success: bool
    message: str
    admin_id: UUID
    role: Optional[str]
    access_token: str
    token_type: str


class AdminProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    admin_user_id: UUID
    full_name: Optional[str]
    email: str
    role: Optional[str]
    is_active: bool
    last_login_at: Optional[datetime]
    created_at: Optional[datetime]


class AdminChangePasswordRequest(BaseModel):
    current_password: str = Field(..., max_length=128)
    new_password: str = Field(..., min_length=10, max_length=128)


class AdminApprovalRequest(BaseModel):
    note: Optional[str] = Field(None, min_length=3, max_length=500, description="Reason shown to the applicant")


# ── User Management ───────────────────────────────────────

class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: UUID
    full_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    phone_verified: bool
    email_verified: bool
    is_profile_completed: bool
    status: str
    created_at: Optional[datetime]
    last_login_at: Optional[datetime]


class AdminUserListResponse(BaseModel):
    success: bool
    total: int
    users: List[AdminUserResponse]


class AdminUpdateUserStatusRequest(BaseModel):
    status: Literal["active", "inactive", "suspended"]
    reason: Optional[str] = Field(None, max_length=500)


class AdminWalletAdjustRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, le=100000, max_digits=12, decimal_places=2)
    type: Literal["credit", "debit"]
    reason: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=500)


# ── Provider Management ───────────────────────────────────

class AdminProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    provider_id: UUID
    full_name: Optional[str]
    business_name: Optional[str]
    mobile_number: str
    city: Optional[str]
    area: Optional[str]
    pincode: Optional[int]
    is_mobile_verified: bool
    is_profile_completed: bool
    meal_service_type: Optional[str]
    fssai_licence: Optional[str]
    daily_meal_quota: Optional[int]
    created_at: Optional[datetime]


class AdminProviderListResponse(BaseModel):
    success: bool
    total: int
    providers: List[AdminProviderResponse]


class AdminUpdateProviderRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=128)
    business_name: Optional[str] = Field(None, min_length=2, max_length=256)
    kitchen_type: Optional[str] = Field(None, max_length=50)
    meal_service_type: Optional[str] = Field(None, max_length=50)
    house_no: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=500)
    landmark: Optional[str] = Field(None, max_length=256)
    city: Optional[str] = Field(None, max_length=128)
    state: Optional[str] = Field(None, max_length=128)
    area: Optional[str] = Field(None, max_length=256)
    pincode: Optional[int] = Field(None, ge=100000, le=999999)
    fssai_licence: Optional[str] = Field(
        None,
        pattern=r"^\d{14}$",
        description="14-digit FSSAI food business licence number"
    )
    daily_meal_quota: Optional[int] = Field(
        None,
        gt=0,
        le=10000,
        description="Meals the kitchen can serve per meal time per day across all packages."
    )


# ── Delivery Boy Management ───────────────────────────────

class AdminDeliveryBoyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    delivery_boy_id: UUID
    full_name: Optional[str]
    mobile_number: str
    is_mobile_verified: bool
    is_active: bool
    vehicle_type: Optional[str]
    vehicle_number: Optional[str]
    assigned_provider_reference_id: Optional[UUID]
    created_at: Optional[datetime]


class AdminDeliveryBoyListResponse(BaseModel):
    success: bool
    total: int
    delivery_boys: List[AdminDeliveryBoyResponse]


class AdminUpdateDeliveryBoyRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=128)
    vehicle_type: Optional[Literal["bike", "cycle", "scooter", "car"]] = None
    vehicle_number: Optional[str] = Field(None, min_length=4, max_length=20, pattern=r"^[A-Za-z0-9 -]+$")
    is_active: Optional[bool] = None


class AdminDocumentReviewRequest(BaseModel):
    status: Literal["verified", "rejected"]
    remarks: Optional[str] = Field(None, max_length=500, description="Required when rejecting")


# ── Package Management ────────────────────────────────────

class AdminPackageItemRequest(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=255)
    quantity: Optional[str] = Field(None, max_length=50)


class AdminCreatePackageRequest(BaseModel):
    category_id: UUID
    package_name: str = Field(..., min_length=2, max_length=255)
    short_description: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    meal_type: Union[str, List[str]] = Field(
        ...,
        description=(
            "Meal slots — one, any two, or all three. List ([\"lunch\", \"dinner\"]), "
            "comma separated string, or \"full_day\" for all three."
        ),
        examples=[["lunch", "dinner"]]
    )
    food_type: Union[str, List[str]] = Field(..., description="veg | non_veg | egg | vegan | jain (one or more)")

    @field_validator("meal_type", mode="after")
    @classmethod
    def _normalize_meal_type(cls, value):
        return normalize_meal_type(value)

    @field_validator("food_type", mode="after")
    @classmethod
    def _normalize_food_type(cls, value):
        return normalize_food_type(value)

    # base price (MRP) per meal
    price: Decimal = Field(..., gt=0, le=100000)
    # selling price for one-time orders, <= price; omit for no discount
    discounted_price: Optional[Decimal] = Field(None, gt=0, le=100000)
    is_subscription_available: bool = False
    # per-meal price for subscriptions, <= price
    subscription_price: Optional[Decimal] = Field(None, gt=0, le=100000)
    items: List[AdminPackageItemRequest] = Field(..., min_length=1, max_length=50)

    @field_validator("discounted_price", "subscription_price", mode="before")
    @classmethod
    def _zero_none(cls, value):
        return _zero_is_none(value)


class AdminPackageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    package_id: UUID
    provider_reference_id: Optional[UUID]
    category_reference_id: Optional[UUID]
    package_name: str
    description: Optional[str]
    price: Decimal
    discounted_price: Optional[Decimal]
    is_active: bool
    is_available: bool
    is_predefined: bool
    created_at: Optional[datetime]


class AdminPackageListResponse(BaseModel):
    success: bool
    total: int
    packages: List[AdminPackageResponse]


class AdminUpdatePackageRequest(BaseModel):
    package_name: Optional[str] = Field(None, min_length=2, max_length=255)
    short_description: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    meal_type: Optional[Union[str, List[str]]] = None
    food_type: Optional[Union[str, List[str]]] = None
    price: Optional[Decimal] = Field(None, gt=0, le=100000)
    # send 0 to clear the discount
    discounted_price: Optional[Decimal] = Field(None, ge=0, le=100000)
    subscription_price: Optional[Decimal] = Field(None, ge=0, le=100000)
    is_active: Optional[bool] = None
    is_available: Optional[bool] = None

    @field_validator("meal_type", mode="after")
    @classmethod
    def _normalize_meal_type(cls, value):
        return normalize_meal_type(value) if value is not None else None

    @field_validator("food_type", mode="after")
    @classmethod
    def _normalize_food_type(cls, value):
        return normalize_food_type(value) if value is not None else None


class AdminPackageSubscriptionToggleRequest(BaseModel):
    is_subscription_available: bool = Field(
        ...,
        description="true = users can subscribe to this package; false = blocks new subscriptions / switches to it"
    )
    subscription_price: Optional[Decimal] = Field(
        None, gt=0, le=100000,
        description="Per-meal subscription price. Optional: without it subscriptions are charged the selling price."
    )


# ── Subscription Plan Management ──────────────────────────

PLAN_TYPES = ("weekly", "fortnightly", "monthly", "quarterly", "half_yearly", "annually", "custom")


class AdminCreatePlanRequest(BaseModel):
    subscription_type: Literal["weekly", "fortnightly", "monthly", "quarterly", "half_yearly", "annually", "custom"]
    meal_slot: str = Field(
        ...,
        max_length=30,
        description=(
            "breakfast | lunch | dinner | breakfast_lunch | lunch_dinner | breakfast_dinner | all_slots"
        ),
    )
    # ignored for custom plans (the customer picks the dates)
    duration_days: int = Field(0, ge=0, le=366)
    free_skips: int = Field(0, ge=0, le=60)
    discount_percent: Decimal = Field(Decimal("0"), ge=0, le=90, max_digits=5, decimal_places=2)


class AdminPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    subscription_plan_id: UUID
    subscription_type: str
    meal_slot: str
    duration_days: int
    free_skips: int
    discount_percent: Decimal
    is_active: bool
    created_at: Optional[datetime]


class AdminPlanListResponse(BaseModel):
    success: bool
    total: int
    plans: List[AdminPlanResponse]


class AdminUpdatePlanRequest(BaseModel):
    free_skips: Optional[int] = Field(None, ge=0, le=60)
    discount_percent: Optional[Decimal] = Field(None, ge=0, le=90, max_digits=5, decimal_places=2)
    duration_days: Optional[int] = Field(None, gt=0, le=366)
    is_active: Optional[bool] = None


# ── Complaint Management ──────────────────────────────────

class AdminComplaintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    complaint_id: UUID
    against: str
    status: str
    subject: str
    description: str
    evidence_urls: Optional[List[str]]
    admin_notes: Optional[str]
    resolution: Optional[str]
    resolved_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class AdminComplaintListItem(BaseModel):
    id: UUID
    complainant_type: str   # 'user' | 'provider'
    complainant_id: UUID
    against: str
    status: str
    subject: str
    created_at: Optional[datetime]


class AdminComplaintListResponse(BaseModel):
    success: bool
    total: int
    complaints: List[AdminComplaintListItem]


class AdminResolveComplaintRequest(BaseModel):
    status: Literal["in_progress", "resolved", "rejected", "closed"]
    admin_notes: Optional[str] = Field(None, max_length=1000)
    resolution: Optional[str] = Field(None, max_length=2000)


# ── Review Management ─────────────────────────────────────

class AdminReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    review_id: UUID
    user_reference_id: UUID
    vendor_reference_id: UUID
    vendor_rating: int
    package_rating: Optional[int]
    review_text: Optional[str]
    review_date: Optional[date]
    is_visible: bool
    created_at: Optional[datetime]


class AdminReviewListResponse(BaseModel):
    success: bool
    total: int
    reviews: List[AdminReviewResponse]


# ── Order Management ──────────────────────────────────────

class AdminOrderListResponse(BaseModel):
    success: bool
    total: int
    orders: List[Any]


class AdminForceStatusRequest(BaseModel):
    status: str = Field(..., max_length=30)
    # every forced change is audited with its reason
    reason: str = Field(..., min_length=5, max_length=500)


class AdminAssignDeliveryBoyRequest(BaseModel):
    delivery_boy_id: UUID
    reason: Optional[str] = Field(None, max_length=500)


class AdminReassignProviderRequest(BaseModel):
    new_provider_id: UUID
    reason: Optional[str] = Field(None, max_length=500)


class AdminMarkUnavailabilityRequest(BaseModel):
    date: date
    reason: Optional[str] = Field(None, max_length=500)


class AdminProviderUnavailabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    provider_unavailability_id: int
    provider_reference_id: UUID
    unavailable_date: date
    reason: Optional[str]
    created_at: Optional[datetime]


# ── Serviceable Pincodes ──────────────────────────────────

class AdminPincodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pincode_id: int
    pincode: int
    city: str
    state: str
    is_active: bool
    created_at: Optional[datetime]


class AdminPincodeListResponse(BaseModel):
    success: bool
    total: int
    pincodes: List[AdminPincodeResponse]


class AdminCreatePincodeRequest(BaseModel):
    pincode: int = Field(..., ge=100000, le=999999)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)


class AdminUpdatePincodeRequest(BaseModel):
    city: Optional[str] = Field(None, min_length=2, max_length=100)
    state: Optional[str] = Field(None, min_length=2, max_length=100)
    is_active: Optional[bool] = None


# ── Dashboard ─────────────────────────────────────────────

class AdminDashboardResponse(BaseModel):
    success: bool
    users: dict
    providers: dict
    delivery_boys: dict
    subscriptions: dict
    orders: dict
    complaints: dict
    revenue: dict


# ── Pricing configuration ─────────────────────────────────

class AdminPricingComponentUpdate(BaseModel):
    label: Optional[str] = Field(None, min_length=2, max_length=100)
    calc_type: Literal["fixed", "percentage"]
    value: Decimal = Field(..., ge=0, le=100000, max_digits=12, decimal_places=2)
    applies_to: Literal["all", "subscription", "extra_order"] = "all"
    charge_basis: Literal["per_unit", "per_delivery", "per_order"] = "per_delivery"
    is_active: bool = True
    change_reason: str = Field(..., min_length=5, max_length=500)

    @field_validator("value")
    @classmethod
    def _percent_cap(cls, value, info):
        if info.data.get("calc_type") == "percentage" and value > 100:
            raise ValueError("A percentage cannot exceed 100")
        return value


class AdminPricingPreviewRequest(BaseModel):
    kind: Literal["subscription", "extra_order"] = "subscription"
    base_unit_price: Decimal = Field(..., gt=0, le=100000)
    quantity: int = Field(1, ge=1, le=5)
    deliveries: int = Field(1, ge=1, le=1100)
    discount_percent: Decimal = Field(Decimal("0"), ge=0, le=90)


# ── Withdrawals ───────────────────────────────────────────

class AdminProcessPayoutRequest(BaseModel):
    action: Literal["paid", "rejected"]
    payout_reference: Optional[str] = Field(None, min_length=4, max_length=100, pattern=r"^[A-Za-z0-9/_.-]+$")
    admin_note: Optional[str] = Field(None, max_length=500)


# ── Payments ──────────────────────────────────────────────

class AdminReverseTopupRequest(BaseModel):
    amount: Optional[Decimal] = Field(None, gt=0, le=100000, max_digits=12, decimal_places=2)
    reason: str = Field(..., min_length=5, max_length=255)
