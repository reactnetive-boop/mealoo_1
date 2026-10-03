from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import limit_by_ip
from app.dependencies.auth_dependency import get_delivery_session
from app.services.delivery_boy_auth_service import DeliveryBoyAuthService
from app.schemas.delivery_boy_schema import (
    DeliveryBoyRegisterRequest,
    DeliveryBoyRegisterResponse,
    DeliveryBoyVerifyOTPRequest,
    DeliveryBoyLoginRequest,
    DeliveryBoyAuthResponse,
    DeliveryBoyForgotPasswordRequest,
    DeliveryBoyResetPasswordRequest,
)
from app.schemas.auth_schema import LogoutResponse, ChangePasswordRequest

router = APIRouter()


@router.post(
    "/register",
    response_model=DeliveryBoyRegisterResponse,
    summary="Delivery Boy Register – Step 1: Send OTP",
    description=(
        "Rejected with 409 if the number is already registered. The OTP is echoed only "
        "outside production (no SMS gateway yet)."
    ),
    dependencies=[Depends(limit_by_ip("delivery_otp", 10, 600))],
)
def register(payload: DeliveryBoyRegisterRequest, db: Session = Depends(get_db)):
    return DeliveryBoyAuthService.generate_otp(db, payload.mobile_number, payload.password)


@router.post(
    "/verify-otp",
    response_model=DeliveryBoyAuthResponse,
    summary="Delivery Boy Register – Step 2: Verify OTP",
    description=(
        "Creates the partner account and signs in. New partners are 'pending' until an admin "
        "verifies their documents and approves them; call `GET /delivery/me/state` next."
    ),
    dependencies=[Depends(limit_by_ip("delivery_verify", 20, 600))],
)
def verify_otp(payload: DeliveryBoyVerifyOTPRequest, db: Session = Depends(get_db)):
    return DeliveryBoyAuthService.verify_otp(db, payload.mobile_number, payload.otp)


@router.post(
    "/login",
    response_model=DeliveryBoyAuthResponse,
    summary="Delivery Boy Login",
    dependencies=[Depends(limit_by_ip("delivery_login", 20, 300))],
)
def login(payload: DeliveryBoyLoginRequest, db: Session = Depends(get_db)):
    return DeliveryBoyAuthService.login(db, payload.mobile_number, payload.password)


@router.post(
    "/forgot-password/send-otp",
    summary="Forgot Password – Step 1",
    dependencies=[Depends(limit_by_ip("delivery_forgot", 10, 600))],
)
def forgot_password_send_otp(payload: DeliveryBoyForgotPasswordRequest, db: Session = Depends(get_db)):
    return DeliveryBoyAuthService.forgot_password_send_otp(db, payload.mobile_number)


@router.post(
    "/forgot-password/verify-otp",
    summary="Forgot Password – Step 2 (returns reset_token)",
    dependencies=[Depends(limit_by_ip("delivery_forgot_verify", 20, 600))],
)
def forgot_password_verify(payload: DeliveryBoyVerifyOTPRequest, db: Session = Depends(get_db)):
    return DeliveryBoyAuthService.forgot_password_verify_otp(db, payload.mobile_number, payload.otp)


@router.post(
    "/forgot-password/reset",
    summary="Forgot Password – Step 3",
    dependencies=[Depends(limit_by_ip("delivery_reset", 10, 600))],
)
def forgot_password_reset(payload: DeliveryBoyResetPasswordRequest, db: Session = Depends(get_db)):
    return DeliveryBoyAuthService.reset_password(
        db, payload.mobile_number, payload.reset_token, payload.new_password, payload.confirm_password
    )


@router.put("/change-password", summary="Change Password (signs out other sessions)")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current=Depends(get_delivery_session),
):
    return DeliveryBoyAuthService.change_password(
        db, current["delivery_boy_id"], payload.current_password, payload.new_password
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Delivery Boy Logout",
    description="Invalidates every token issued so far and marks the partner offline.",
)
def logout_delivery_boy(db: Session = Depends(get_db), current=Depends(get_delivery_session)):
    return DeliveryBoyAuthService.logout_delivery_boy(db, current["delivery_boy_id"])
