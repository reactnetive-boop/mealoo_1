from typing import List, Optional, Any, Union
from uuid import UUID
from decimal import Decimal
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator

from app.utils.meal_type import normalize_meal_type


# ── Auth ──────────────────────────────────────────────────

class AdminLoginRequest(BaseModel):
    email: str
    password: str


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
    current_password: str
    new_password: str = Field(..., min_length=6)


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
    status: str = Field(..., description="active | inactive | suspended")
    reason: Optional[str] = Field(None, max_length=500)


class AdminWalletAdjustRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    type: str = Field(..., description="credit or debit")
    reason: str = Field(..., max_length=255)
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
    created_at: Optional[datetime]


class AdminProviderListResponse(BaseModel):
    success: bool
    total: int
    providers: List[AdminProviderResponse]


class AdminUpdateProviderRequest(BaseModel):
    full_name: Optional[str] = Field(None, max_length=128)
    business_name: Optional[str] = Field(None, max_length=256)
    city: Optional[str] = Field(None, max_length=128)
    area: Optional[str] = Field(None, max_length=256)
    pincode: Optional[int] = None
    is_profile_completed: Optional[bool] = None


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
    full_name: Optional[str] = Field(None, max_length=128)
    vehicle_type: Optional[str] = None
    vehicle_number: Optional[str] = Field(None, max_length=20)
    assigned_provider_id: Optional[UUID] = None
    is_active: Optional[bool] = None


# ── Package Management ────────────────────────────────────

class AdminPackageItemRequest(BaseModel):
    item_name: str
    quantity: Optional[str] = None


class AdminCreatePackageRequest(BaseModel):
    category_id: UUID
    package_name: str = Field(..., max_length=255)
    short_description: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    meal_type: Union[str, List[str]] = Field(
        ...,
        description=(
            "Meal slots — one, any two, or all three. List ([\"lunch\", \"dinner\"]), "
            "comma separated string, or \"full_day\" for all three."
        ),
        examples=[["lunch", "dinner"]]
    )
    food_type: str = Field(..., description="veg | non_veg | egg")

    @field_validator("meal_type", mode="after")
    @classmethod
    def _normalize_meal_type(cls, value):
        return normalize_meal_type(value)
    price: Decimal = Field(..., gt=0)
    discounted_price: Optional[Decimal] = Field(None, ge=0)
    is_subscription_available: bool = False
    subscription_price: Optional[Decimal] = Field(None, ge=0)
    items: List[AdminPackageItemRequest] = Field(..., min_length=1)


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
    package_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, gt=0)
    discounted_price: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = None
    is_available: Optional[bool] = None


class AdminPackageSubscriptionToggleRequest(BaseModel):
    is_subscription_available: bool = Field(
        ...,
        description="true = users can subscribe to this package; false = blocks new subscriptions / switches to it"
    )
    subscription_price: Optional[Decimal] = Field(
        None, ge=0,
        description="Per-meal subscription price. Required when enabling if the package has no subscription_price yet."
    )


# ── Subscription Plan Management ──────────────────────────

class AdminCreatePlanRequest(BaseModel):
    subscription_type: str = Field(..., description="monthly | weekly | custom")
    meal_slot: str = Field(..., description="breakfast | lunch | dinner | all")
    duration_days: int = Field(..., gt=0)
    free_skips: int = Field(0, ge=0)
    discount_percent: Decimal = Field(Decimal("0"), ge=0, le=100)


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
    free_skips: Optional[int] = Field(None, ge=0)
    discount_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    duration_days: Optional[int] = Field(None, gt=0)
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
    status: str = Field(..., description="in_progress | resolved | rejected | closed")
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
    status: str
    reason: Optional[str] = Field(None, max_length=500)


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
    pincode: int
    city: str = Field(..., max_length=100)
    state: str = Field(..., max_length=100)


class AdminUpdatePincodeRequest(BaseModel):
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
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
