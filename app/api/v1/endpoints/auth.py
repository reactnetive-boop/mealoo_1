from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import limit_by_ip
from app.dependencies.auth_dependency import get_provider_session
from app.schemas.auth_schema import (
    GenerateOTPRequest,
    VerifyOTPRequest,
    ForgotPasswordOTPRequest,
    ForgotPasswordOTPResponse,
    ForgotPasswordVerifyResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    LoginRequest,
    LogoutResponse,
    ChangePasswordRequest,
)
from app.services.auth_service import AuthService


router = APIRouter()


@router.post(
    "/generate-otp",
    summary="Provider Register – Step 1: Send OTP",
    description=(
        "**First step of kitchen registration.** Rejected with 409 if the number is already "
        "registered (use Forgot Password instead). The OTP is returned in the response only "
        "outside production, until an SMS gateway is connected.\n\n"
        "**Flow:** `POST /generate-otp` → `POST /verify-otp` → `POST /login` → "
        "`PUT /provider/complete-profile`"
    ),
    dependencies=[Depends(limit_by_ip("provider_otp", 10, 600))],
)
def generate_otp(request: GenerateOTPRequest, db: Session = Depends(get_db)):
    return AuthService.generate_otp(db, request.mobile_number, request.password)


@router.post(
    "/verify-otp",
    summary="Provider Register – Step 2: Verify OTP",
    description="Creates the kitchen account. Never changes an existing account.",
    dependencies=[Depends(limit_by_ip("provider_verify", 20, 600))],
)
def verify_otp(request: VerifyOTPRequest, db: Session = Depends(get_db)):
    return AuthService.verify_otp(db, request.mobile_number, request.otp)


@router.post(
    "/forgot-password/send-otp",
    response_model=ForgotPasswordOTPResponse,
    summary="Forgot Password - Step 1: Send OTP",
    description="Responds the same way whether or not the number is registered.",
    dependencies=[Depends(limit_by_ip("provider_forgot", 10, 600))],
)
def forgot_password_send_otp(request: ForgotPasswordOTPRequest, db: Session = Depends(get_db)):
    return AuthService.forgot_password_send_otp(db, request.mobile_number)


@router.post(
    "/forgot-password/verify-otp",
    response_model=ForgotPasswordVerifyResponse,
    summary="Forgot Password - Step 2: Verify OTP",
    description="Returns a one-time `reset_token` that step 3 must present.",
    dependencies=[Depends(limit_by_ip("provider_forgot_verify", 20, 600))],
)
def forgot_password_verify(request: VerifyOTPRequest, db: Session = Depends(get_db)):
    return AuthService.forgot_password_verify_otp(db, request.mobile_number, request.otp)


@router.post(
    "/forgot-password/reset",
    response_model=ResetPasswordResponse,
    summary="Forgot Password - Step 3: Set New Password",
    description="Requires the `reset_token` from step 2. Signs the kitchen out everywhere.",
    dependencies=[Depends(limit_by_ip("provider_reset", 10, 600))],
)
def forgot_password_reset(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    return AuthService.reset_password(
        db,
        request.mobile_number,
        request.reset_token,
        request.new_password,
        request.confirm_password,
    )


@router.post(
    "/login",
    summary="Provider Login",
    description=(
        "Returns a JWT `access_token`. After login call `GET /provider/me/state` to decide which "
        "screen to show."
    ),
    dependencies=[Depends(limit_by_ip("provider_login", 20, 300))],
)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    return AuthService.login(db, request.mobile_number, request.password)


@router.put("/change-password", summary="Change Password (signs out other sessions)")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current=Depends(get_provider_session),
):
    return AuthService.change_password(db, current["provider_id"], payload.current_password, payload.new_password)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Provider Logout",
    description="Invalidates every token issued to this kitchen so far.",
)
def logout_provider(db: Session = Depends(get_db), current=Depends(get_provider_session)):
    return AuthService.logout(db, current["provider_id"])
