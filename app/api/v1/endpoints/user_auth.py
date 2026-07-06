from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.dependencies.provider_dependency import get_db
from app.schemas.user_auth_schema import (
    UserGenerateOTPRequest,
    UserVerifyOTPRequest,
    UserLoginRequest
)
from app.schemas.auth_schema import LogoutResponse
from app.services.user_auth_service import UserAuthService

router = APIRouter()


@router.post(
    "/generate-otp",
    summary="Register – Step 1: Send OTP",
    description=(
        "**First step of user registration.**\n\n"
        "Provide your mobile number, email, and a password. "
        "An OTP is sent to your phone. "
        "Call `/verify-otp` next with the same mobile number and the OTP received.\n\n"
        "**Flow:** `POST /generate-otp` → `POST /verify-otp` → `POST /login`"
    )
)
def generate_otp(
    request: UserGenerateOTPRequest,
    db: Session = Depends(get_db)
):

    try:

        return UserAuthService.generate_otp(
            db,
            request.phone,
            request.email,
            request.password
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post(
    "/verify-otp",
    summary="Register – Step 2: Verify OTP",
    description=(
        "**Second step of user registration.**\n\n"
        "Submit the OTP received on your mobile number to verify your account. "
        "On success the account is activated and you can log in.\n\n"
        "**Flow:** `POST /generate-otp` → `POST /verify-otp` → `POST /login`"
    )
)
def verify_otp(
    request: UserVerifyOTPRequest,
    db: Session = Depends(get_db)
):

    try:

        return UserAuthService.verify_otp(
            db,
            request.phone,
            request.email,
            request.otp
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post(
    "/login",
    summary="User Login",
    description=(
        "**Login with phone number and password.**\n\n"
        "Returns a JWT `access_token`. Include this token in the `Authorization` header "
        "as `Bearer <token>` for all authenticated endpoints.\n\n"
        "**When to call:** After OTP verification (registration) or on every app open / session start.\n\n"
        "**Flow:** `POST /verify-otp` → `POST /login` → use `access_token` in all subsequent calls"
    )
)
def login(
    request: UserLoginRequest,
    db: Session = Depends(get_db)
):

    try:

        return UserAuthService.login(
            db,
            request.phone,
            None,
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
    summary="User Logout",
    description=(
        "**Invalidate the current user session.**\n\n"
        "Call this when the user logs out of the app. "
        "The client should discard the stored token after this call."
    )
)
async def logout_user():

    return await UserAuthService.logout_user()
