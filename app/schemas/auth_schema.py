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