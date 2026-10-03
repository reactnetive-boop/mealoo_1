from pydantic import BaseModel
from pydantic import Field

MOBILE_PATTERN = r"^[6-9]\d{9}$"


class GenerateOTPRequest(BaseModel):

    mobile_number: str = Field(
        ...,
        pattern=MOBILE_PATTERN,
        description="10 digit Indian mobile number"
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=64
    )


class VerifyOTPRequest(BaseModel):

    mobile_number: str = Field(
        ...,
        pattern=MOBILE_PATTERN
    )

    otp: str = Field(
        ...,
        pattern=r"^\d{6}$"
    )


class ForgotPasswordOTPRequest(BaseModel):

    mobile_number: str = Field(
        ...,
        pattern=MOBILE_PATTERN,
        description="Registered 10 digit mobile number"
    )


class ForgotPasswordOTPResponse(BaseModel):

    success: bool

    mobile_number: str

    message: str

    # Only outside production (no SMS gateway yet)
    otp: str | None = None


class ForgotPasswordVerifyResponse(BaseModel):

    success: bool

    message: str

    # One-time token required by the reset call (valid for a few minutes)
    reset_token: str


class ResetPasswordRequest(BaseModel):

    mobile_number: str = Field(
        ...,
        pattern=MOBILE_PATTERN,
        description="10 digit mobile number whose OTP was just verified"
    )

    reset_token: str = Field(
        ...,
        min_length=20,
        max_length=200,
        description="Token returned by forgot-password/verify-otp"
    )

    new_password: str = Field(
        ...,
        min_length=8,
        max_length=64
    )

    confirm_password: str = Field(
        ...,
        min_length=8,
        max_length=64
    )


class ResetPasswordResponse(BaseModel):

    success: bool

    message: str

    provider_id: str | None = None


class LoginRequest(BaseModel):

    mobile_number: str = Field(
        ...,
        min_length=10,
        max_length=10,
        description="10 digit mobile number"
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=64
    )


class ChangePasswordRequest(BaseModel):

    current_password: str = Field(..., min_length=1, max_length=64)

    new_password: str = Field(..., min_length=8, max_length=64)


class LogoutResponse(BaseModel):
    success: bool
    message: str
