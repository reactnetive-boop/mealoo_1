from pydantic import BaseModel
from pydantic import Field


class GenerateOTPRequest(BaseModel):

    mobile_number: str = Field(
        ...,
        min_length=10,
        max_length=10,
        description="10 digit mobile number"
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=16
    )

class VerifyOTPRequest(BaseModel):

    mobile_number: str = Field(
        ...,
        min_length=10,
        max_length=10
    )

    otp: str = Field(
        ...,
        min_length=6,
        max_length=6
    )

class ForgotPasswordOTPRequest(BaseModel):

    mobile_number: str = Field(
        ...,
        min_length=10,
        max_length=10,
        description="Registered 10 digit mobile number of the provider"
    )


class ForgotPasswordOTPResponse(BaseModel):

    success: bool

    mobile_number: str

    message: str

    # Returned only while SMS delivery is not wired up
    otp: str


class ResetPasswordRequest(BaseModel):

    mobile_number: str = Field(
        ...,
        min_length=10,
        max_length=10,
        description="10 digit mobile number whose OTP was just verified"
    )

    new_password: str = Field(
        ...,
        min_length=8,
        max_length=16
    )

    confirm_password: str = Field(
        ...,
        min_length=8,
        max_length=16
    )


class ResetPasswordResponse(BaseModel):

    success: bool

    message: str

    provider_id: str


class LoginRequest(BaseModel):
    
    mobile_number: str = Field(
        ...,
        min_length=10,
        max_length=10,
        description="10 digit mobile number"
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=16
    )

class LogoutResponse(BaseModel):
    success: bool
    message: str    