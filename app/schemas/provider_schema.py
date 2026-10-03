from pydantic import BaseModel, Field
from typing import Optional
from datetime import date
from uuid import UUID
from enum import Enum as PyEnum

class MealServiceType(str, PyEnum):
    BREAKFAST = "Breakfast"
    LUNCH = "Lunch"
    DINNER = "Dinner"
    LUNCH_AND_DINNER = "Lunch and Dinner"
    LUNCH_AND_BREAKFAST = "Lunch and Breakfast"
    BREAKFAST_AND_DINNER = "Breakfast and Dinner"
    LUNCH_DINNER_BREAKFAST = "Lunch and Dinner and Breakfast"
    FULL_DAY = "Full Day"

class CompleteProfileRequest(
    BaseModel
):

    full_name: str = Field(..., min_length=2, max_length=128)

    business_name: str = Field(..., min_length=2, max_length=256)

    city: str = Field(..., min_length=2, max_length=128)

    area: str = Field(..., min_length=2, max_length=256)

    address: str = Field(..., min_length=5, max_length=500)

    kitchen_type: str = Field(..., min_length=2, max_length=128)

    pincode: int = Field(..., ge=100000, le=999999)

    house_no: str = Field(..., min_length=1, max_length=64)

    landmark: Optional[str] = Field(None, max_length=128)

    state: str = Field(..., min_length=2, max_length=128)

    meal_service_type: MealServiceType

    fssai_licence: Optional[str] = Field(
        None,
        pattern=r"^\d{14}$",
        description="14-digit FSSAI food business licence number"
    )

    daily_meal_quota: int = Field(
        ...,
        gt=0,
        le=10000,
        description=(
            "Meals this kitchen can serve per meal-slot per day across all packages "
            "(e.g. 15 = 15 breakfasts, 15 lunches and 15 dinners)."
        )
    )

class ProviderProfileResponse(
    BaseModel
):

    provider_id: UUID

    mobile_number: str

    full_name: Optional[str]

    business_name: Optional[str]

    city: Optional[str]

    area: Optional[str]

    address: Optional[str]

    kitchen_type: Optional[str]

    pincode: Optional[int]

    house_no: Optional[str]

    landmark: Optional[str]

    state: Optional[str]

    is_profile_completed: bool

    meal_service_type: Optional[MealServiceType]

    fssai_licence: Optional[str] = None

    daily_meal_quota: Optional[int] = None

    profile_image: Optional[str] = None

    is_active: bool = True

    is_accepting_orders: bool = True

    approval_status: str = "pending"

    approval_note: Optional[str] = None


class UpdateDailyQuotaRequest(BaseModel):

    daily_meal_quota: Optional[int] = Field(
        ...,
        gt=0,
        description=(
            "Meals servable per meal-slot per day across all packages. "
            "Send null to remove the limit."
        )
    )


class DailyQuotaSlotStatus(BaseModel):

    subscription_committed: int

    extra_orders: int

    total_committed: int

    available: Optional[int]

    is_full: bool


class DailyQuotaStatusResponse(BaseModel):

    success: bool

    daily_meal_quota: Optional[int]

    date: date

    slots: dict[str, DailyQuotaSlotStatus]


class UpdateDailyQuotaResponse(BaseModel):

    success: bool

    message: str

    daily_meal_quota: Optional[int]

    current_peak_demand: int


class UpdateProfileImageResponse(
    BaseModel
):

    success: bool

    message: str

    profile_image: str

class ProviderAddressUpdateRequest(BaseModel):
    # The kitchen always comes from the login session; a provider_id sent by
    # older app versions is ignored.
    provider_id: Optional[str] = None
    house_no: str = Field(..., min_length=1, max_length=64)
    address: str = Field(..., min_length=5, max_length=500)
    landmark: Optional[str] = Field(None, max_length=128)
    area: Optional[str] = Field(None, max_length=256)
    city: str = Field(..., min_length=2, max_length=128)
    state: str = Field(..., min_length=2, max_length=128)
    pincode: int = Field(..., ge=100000, le=999999)


class AcceptingOrdersRequest(BaseModel):
    accepting: bool


class HolidayRequest(BaseModel):
    date: date
    reason: Optional[str] = Field(None, max_length=500)
