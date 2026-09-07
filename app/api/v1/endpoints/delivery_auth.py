from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.delivery_boy_auth_service import DeliveryBoyAuthService
from app.schemas.delivery_boy_schema import (
    DeliveryBoyRegisterRequest,
    DeliveryBoyRegisterResponse,
    DeliveryBoyVerifyOTPRequest,
    DeliveryBoyLoginRequest,
    DeliveryBoyAuthResponse,
)
from app.schemas.auth_schema import LogoutResponse

router = APIRouter()


@router.post(
    "/register",
    response_model=DeliveryBoyRegisterResponse,
    summary="Delivery Boy Register – Step 1: Send OTP",
    description=(
        "**First step of delivery boy registration.**\n\n"
        "Provide a mobile number and password. An OTP is sent to the mobile. "
        "The delivery boy account is pre-assigned to a provider by the admin. "
        "Call `/delivery/verify-otp` next with the received OTP.\n\n"
        "**Flow:** `POST /delivery/register` → `POST /delivery/verify-otp` → `POST /delivery/login`"
    )
)
def register(
    payload: DeliveryBoyRegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        return DeliveryBoyAuthService.generate_otp(
            db,
            payload.mobile_number,
            payload.password
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/verify-otp",
    response_model=DeliveryBoyAuthResponse,
    summary="Delivery Boy Register – Step 2: Verify OTP",
    description=(
        "**Second step of delivery boy registration.**\n\n"
        "Submit the OTP received during registration to activate the account. "
        "On success the account is active and the delivery boy can log in.\n\n"
        "**Flow:** `POST /delivery/register` → `POST /delivery/verify-otp` → `POST /delivery/login`"
    )
)
def verify_otp(
    payload: DeliveryBoyVerifyOTPRequest,
    db: Session = Depends(get_db)
):
    return DeliveryBoyAuthService.verify_otp(db, payload.mobile_number, payload.otp)


@router.post(
    "/login",
    response_model=DeliveryBoyAuthResponse,
    summary="Delivery Boy Login",
    description=(
        "**Login for delivery personnel using mobile number and password.**\n\n"
        "Returns a JWT `access_token`. Include this in all delivery API calls as "
        "`Authorization: Bearer <token>`.\n\n"
        "**After login:** Call `GET /delivery/profile` to load the delivery boy's details "
        "and `GET /delivery/orders` to see today's assigned deliveries."
    )
)
def login(
    payload: DeliveryBoyLoginRequest,
    db: Session = Depends(get_db)
):
    return DeliveryBoyAuthService.login(db, payload.mobile_number, payload.password)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Delivery Boy Logout",
    description=(
        "**Invalidate the current delivery boy session.**\n\n"
        "Call this when the delivery boy logs out of the app. "
        "The client should discard the stored token after this call."
    )
)
async def logout_delivery_boy():

    return await DeliveryBoyAuthService.logout_delivery_boy()
