from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.dependencies.provider_dependency import (
    get_db
)

from app.schemas.auth_schema import (
    GenerateOTPRequest, VerifyOTPRequest,
    ForgotPasswordOTPRequest, ForgotPasswordOTPResponse,
    ResetPasswordRequest, ResetPasswordResponse
)


from app.services.auth_service import (
    AuthService
)

from app.schemas.auth_schema import LoginRequest
from app.schemas.auth_schema import LogoutResponse


router = APIRouter()


@router.post(
    "/generate-otp",
    summary="Provider Register – Step 1: Send OTP",
    description=(
        "**First step of provider (vendor/kitchen) registration.**\n\n"
        "Provide a mobile number and password. An OTP is sent to the mobile number. "
        "Call `/provider/verify-otp` next with the same mobile and the received OTP.\n\n"
        "**Flow:** `POST /generate-otp` → `POST /verify-otp` → `POST /login` → "
        "`PUT /provider/complete-profile`"
    )
)
def generate_otp(
    request: GenerateOTPRequest,
    db: Session = Depends(get_db)
):

    try:

        return AuthService.generate_otp(
            db,
            request.mobile_number,
            request.password
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post(
    "/verify-otp",
    summary="Provider Register – Step 2: Verify OTP",
    description=(
        "**Second step of provider registration.**\n\n"
        "Submit the OTP received on the registered mobile number. "
        "On success the provider account is activated and can log in.\n\n"
        "**Flow:** `POST /generate-otp` → `POST /verify-otp` → `POST /login`"
    )
)
def verify_otp(
    request: VerifyOTPRequest,
    db: Session = Depends(get_db)
):

    try:

        return AuthService.verify_otp(
            db,
            request.mobile_number,
            request.otp
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post(
    "/forgot-password/send-otp",
    response_model=ForgotPasswordOTPResponse,
    summary="Forgot Password - Step 1: Send OTP",
    description=(
        "**First step of provider password recovery.**\n\n"
        "Send only the registered mobile number - no password is required, since the "
        "provider has forgotten it. An OTP is sent to that mobile number.\n\n"
        "Fails with 400 if no provider is registered with the number, or if the account "
        "is deactivated.\n\n"
        "**Flow:** `POST /forgot-password/send-otp` -> `POST /verify-otp` -> "
        "`POST /forgot-password/reset` -> `POST /login` with the new password\n\n"
        "**When to call:** When the provider taps 'Forgot password?' on the login screen."
    )
)
def forgot_password_send_otp(
    request: ForgotPasswordOTPRequest,
    db: Session = Depends(get_db)
):

    try:

        return AuthService.forgot_password_send_otp(
            db,
            request.mobile_number
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post(
    "/forgot-password/reset",
    response_model=ResetPasswordResponse,
    summary="Forgot Password - Step 3: Set New Password",
    description=(
        "**Final step of provider password recovery.**\n\n"
        "Submit `new_password` and `confirm_password` for the mobile number whose OTP was "
        "just verified through `POST /verify-otp` (step 2). The two must match and be "
        "8-16 characters.\n\n"
        "The OTP is single-use: it is burnt once the password is changed, so a second "
        "reset needs a fresh `POST /forgot-password/send-otp`. The request is rejected "
        "with 400 if the OTP was never verified or the 15 minute window has lapsed.\n\n"
        "**When to call:** On the 'Set new password' screen, after OTP verification. "
        "Send the provider to the login screen afterwards - no token is issued here."
    )
)
def forgot_password_reset(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):

    try:

        return AuthService.reset_password(
            db,
            request.mobile_number,
            request.new_password,
            request.confirm_password
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post(
    "/login",
    summary="Provider Login",
    description=(
        "**Login for providers (vendors/kitchens) using mobile number and password.**\n\n"
        "Returns a JWT `access_token`. Include this in all provider API calls as "
        "`Authorization: Bearer <token>`.\n\n"
        "**After first login:** Call `PUT /provider/complete-profile` to fill in business details "
        "before the provider can accept orders."
    )
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):

    try:

        return AuthService.login(
            db,
            request.mobile_number,
            request.password
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Provider Logout",
    description=(
        "**Invalidate the current provider session.**\n\n"
        "Call this when the provider logs out of the app. "
        "The client should discard the stored token after this call."
    )
)
async def logout_provider():

    response = await AuthService.logout_provider()

    return response
