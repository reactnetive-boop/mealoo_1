from typing import Optional

from pydantic import BaseModel
from pydantic import Field

from app.schemas.auth_schema import MOBILE_PATTERN


class UserGenerateOTPRequest(BaseModel):

    phone: str = Field(
        ...,
        pattern=MOBILE_PATTERN,
        description="10 digit Indian mobile number"
    )

    email: Optional[str] = Field(
        None,
        max_length=255,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
        description="Optional email address"
    )

    password: str = Field(
        ...,
        min_length=8,
        max_length=64
    )


class UserVerifyOTPRequest(BaseModel):

    phone: str = Field(
        ...,
        pattern=MOBILE_PATTERN
    )

    email: Optional[str] = Field(
        None,
        max_length=255
    )

    otp: str = Field(
        ...,
        pattern=r"^\d{6}$"
    )


class UserLoginRequest(BaseModel):

    phone: str = Field(
        ...,
        min_length=10,
        max_length=10,
        description="Registered mobile number"
    )

    password: str = Field(
        ...,
        min_length=1,
        max_length=64
    )


class UserForgotPasswordRequest(BaseModel):

    phone: str = Field(..., pattern=MOBILE_PATTERN)


class UserForgotPasswordVerifyRequest(BaseModel):

    phone: str = Field(..., pattern=MOBILE_PATTERN)

    otp: str = Field(..., pattern=r"^\d{6}$")


class UserResetPasswordRequest(BaseModel):

    phone: str = Field(..., pattern=MOBILE_PATTERN)

    reset_token: str = Field(..., min_length=20, max_length=200)

    new_password: str = Field(..., min_length=8, max_length=64)

    confirm_password: str = Field(..., min_length=8, max_length=64)
