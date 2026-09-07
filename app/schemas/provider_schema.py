from pydantic import BaseModel
from typing import Optional
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

    full_name: str

    business_name: str

    city: str

    area: str

    address: str

    kitchen_type: str

    pincode: int

    house_no: Optional[str] = None

    landmark: Optional[str] = None

    state: str

    meal_service_type: Optional[MealServiceType] = None

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


class UpdateProfileImageResponse(
    BaseModel
):

    success: bool

    message: str

    profile_image: str

class ProviderAddressUpdateRequest(BaseModel):

    provider_id: str
    house_no: str
    address: str
    landmark: Optional[str] = None
    city: str
    state: str
    pincode: int    