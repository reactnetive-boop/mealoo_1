from typing import Optional

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator


class UserGenerateOTPRequest(BaseModel):

    phone: Optional[str] = Field(
        None,
        min_length=10,
        max_length=15,
        description="10-15 digit mobile number"
    )

    email: Optional[str] = Field(
        None,
        max_length=255,
        description="User email address"
    )

    password: str = Field(
        ...,
        min_length=8,
        max_length=64
    )

    @model_validator(mode="after")
    def check_phone_or_email(self):
        if not self.phone and not self.email:
            raise ValueError("Either phone or email is required")
        return self


class UserVerifyOTPRequest(BaseModel):

    phone: Optional[str] = Field(
        None,
        min_length=10,
        max_length=15
    )

    email: Optional[str] = Field(
        None,
        max_length=255
    )

    otp: str = Field(
        ...,
        min_length=6,
        max_length=6
    )

    @model_validator(mode="after")
    def check_phone_or_email(self):
        if not self.phone and not self.email:
            raise ValueError("Either phone or email is required")
        return self


class UserLoginRequest(BaseModel):

    phone: str = Field(
        ...,
        min_length=10,
        max_length=15,
        description="Registered mobile number"
    )

    password: str = Field(
        ...,
        min_length=8,
        max_length=64
    )
