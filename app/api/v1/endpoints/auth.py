from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.dependencies.provider_dependency import (
    get_db
)

from app.schemas.auth_schema import (
    GenerateOTPRequest, VerifyOTPRequest
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
