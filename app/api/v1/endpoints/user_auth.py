from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import limit_by_ip
from app.dependencies.auth_dependency import get_current_user
from app.schemas.user_auth_schema import (
    UserGenerateOTPRequest,
    UserVerifyOTPRequest,
    UserLoginRequest,
    UserForgotPasswordRequest,
    UserForgotPasswordVerifyRequest,
    UserResetPasswordRequest,
)
from app.schemas.auth_schema import LogoutResponse, ChangePasswordRequest
from app.services.user_auth_service import UserAuthService

router = APIRouter()


@router.post(
    "/generate-otp",
    summary="Register – Step 1: Send OTP",
    description=(
        "Provide mobile number and password. Rejected with 409 if the number is already "
        "registered. The OTP is echoed only outside production (no SMS gateway yet)."
    ),
    dependencies=[Depends(limit_by_ip("user_otp", 10, 600))],
)
def generate_otp(request: UserGenerateOTPRequest, db: Session = Depends(get_db)):
    return UserAuthService.generate_otp(db, request.phone, request.password)


@router.post(
    "/verify-otp",
    summary="Register – Step 2: Verify OTP",
    description="Creates the account and returns an `access_token`.",
    dependencies=[Depends(limit_by_ip("user_verify", 20, 600))],
)
def verify_otp(request: UserVerifyOTPRequest, db: Session = Depends(get_db)):
    return UserAuthService.verify_otp(db, request.phone, request.otp, email=request.email)


@router.post(
    "/login",
    summary="User Login",
    description="Login with phone number and password. Returns a JWT `access_token`.",
    dependencies=[Depends(limit_by_ip("user_login", 20, 300))],
)
def login(request: UserLoginRequest, db: Session = Depends(get_db)):
    return UserAuthService.login(db, request.phone, request.password)


@router.post(
    "/forgot-password/send-otp",
    summary="Forgot Password – Step 1",
    description="Same response whether or not the number is registered.",
    dependencies=[Depends(limit_by_ip("user_forgot", 10, 600))],
)
def forgot_password_send_otp(request: UserForgotPasswordRequest, db: Session = Depends(get_db)):
    return UserAuthService.forgot_password_send_otp(db, request.phone)


@router.post(
    "/forgot-password/verify-otp",
    summary="Forgot Password – Step 2",
    description="Returns a one-time `reset_token`.",
    dependencies=[Depends(limit_by_ip("user_forgot_verify", 20, 600))],
)
def forgot_password_verify(request: UserForgotPasswordVerifyRequest, db: Session = Depends(get_db)):
    return UserAuthService.forgot_password_verify_otp(db, request.phone, request.otp)


@router.post(
    "/forgot-password/reset",
    summary="Forgot Password – Step 3",
    description="Sets the new password using the `reset_token`; signs out every session.",
    dependencies=[Depends(limit_by_ip("user_reset", 10, 600))],
)
def forgot_password_reset(request: UserResetPasswordRequest, db: Session = Depends(get_db)):
    return UserAuthService.reset_password(
        db, request.phone, request.reset_token, request.new_password, request.confirm_password
    )


@router.put("/change-password", summary="Change Password (signs out other sessions)")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return UserAuthService.change_password(db, current_user["user_id"], payload.current_password, payload.new_password)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="User Logout",
    description="Invalidates every token issued to this account so far.",
)
def logout_user(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return UserAuthService.logout(db, current_user["user_id"])
