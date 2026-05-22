from pydantic import BaseModel
from typing import Optional
from uuid import UUID


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

class UpdateProfileImageResponse(
    BaseModel
):

    success: bool

    message: str

    profile_image: str