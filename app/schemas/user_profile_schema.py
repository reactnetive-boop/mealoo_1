from typing import Optional
from uuid import UUID
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class UserProfileResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID

    phone: Optional[str]

    email: Optional[str]

    full_name: Optional[str]

    gender: Optional[str]

    date_of_birth: Optional[date]

    avatar_url: Optional[str]

    is_profile_completed: bool

    status: str

    referral_code: Optional[str]

    created_at: Optional[datetime]


class UpdateProfileImageResponse(BaseModel):

    success: bool

    message: str

    avatar_url: str


class UpdateUserProfileRequest(BaseModel):

    full_name: Optional[str] = Field(
        None,
        max_length=100
    )

    gender: Optional[str] = Field(
        None,
        description="male | female | other | prefer_not_to_say"
    )

    date_of_birth: Optional[date] = None

    avatar_url: Optional[str] = None

    email: Optional[str] = Field(
        None,
        max_length=255
    )
