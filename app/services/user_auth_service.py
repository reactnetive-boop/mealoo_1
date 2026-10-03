from sqlalchemy.orm import Session

from app.core.audit import security_event
from app.core.clock import now_utc
from app.core.errors import DomainError
from app.core.security import (
    hash_password,
    verify_password,
    burn_password_check,
    create_access_token,
    ROLE_CUSTOMER,
)
from app.models.user_otp_log_model import UserOTPLog
from app.repositories.user_repository import UserRepository
from app.services.auth_common import (
    OtpTable,
    INVALID_CREDENTIALS,
    issue_otp,
    consume_otp,
    issue_reset_token,
    redeem_reset_token,
    otp_response,
    assert_not_locked,
    register_failed_login,
    register_successful_login,
    revoke_sessions,
)

USER_OTP = OtpTable(model=UserOTPLog, identity="contact", code="otp_hash", used="is_used")


def _token(user) -> str:
    return create_access_token(
        {"user_id": str(user.user_id), "contact": user.phone or user.email},
        role=ROLE_CUSTOMER,
        token_version=user.token_version,
    )


class UserAuthService:

    @staticmethod
    def generate_otp(db: Session, phone: str, email: str, password: str):
        """Registration step 1. Existing accounts must log in or reset their password."""

        if UserRepository.get_by_phone(db, phone):
            raise DomainError(
                "This mobile number is already registered. Please log in or use Forgot Password.",
                409,
                code="ALREADY_REGISTERED",
            )

        code = issue_otp(
            db, USER_OTP, phone, "registration",
            channel="sms",
            hashed_password=hash_password(password),
        )
        db.commit()
        return otp_response(code, contact=phone)

    @staticmethod
    def verify_otp(db: Session, phone: str, email: str, otp: str):
        """Registration step 2: creates the account and signs the customer in."""

        row = consume_otp(db, USER_OTP, phone, "registration", otp)

        if UserRepository.get_by_phone(db, phone):
            db.commit()
            raise DomainError("This mobile number is already registered. Please log in.", 409, code="ALREADY_REGISTERED")

        user = UserRepository.create_user(db, {
            "phone": phone,
            "email": email or None,
            "phone_verified": True,
            "email_verified": False,
            "password_hash": row.hashed_password,
            "is_profile_completed": False,
            "status": "active",
        })

        return {
            "success": True,
            "message": "OTP verified successfully",
            "user_id": str(user.user_id),
            "is_profile_completed": user.is_profile_completed,
            "access_token": _token(user),
            "token_type": "bearer",
        }

    @staticmethod
    def login(db: Session, phone: str, email: str, password: str):

        user = UserRepository.get_by_phone(db, phone)
        assert_not_locked(user)

        if user is None or not user.password_hash:
            burn_password_check(password)
            security_event("login.failed", role="customer", identity=phone[-4:])
            raise DomainError(INVALID_CREDENTIALS, 401)

        if not verify_password(password, user.password_hash):
            register_failed_login(db, user, phone)
            raise DomainError(INVALID_CREDENTIALS, 401)

        if user.status != "active":
            raise DomainError(f"Your account is {user.status}. Please contact support.", 403, code="ACCOUNT_INACTIVE")

        register_successful_login(user)
        user.last_login_at = now_utc()
        db.commit()

        return {
            "success": True,
            "message": "Login successful",
            "user_id": str(user.user_id),
            "access_token": _token(user),
            "token_type": "bearer",
        }

    @staticmethod
    def forgot_password_send_otp(db: Session, phone: str):
        user = UserRepository.get_by_phone(db, phone)
        generic = {"success": True, "contact": phone, "message": "If this number is registered, an OTP has been sent."}
        if user is None or user.status != "active":
            security_event("password_reset.unknown_or_inactive", role="customer", identity=phone[-4:])
            return generic
        code = issue_otp(db, USER_OTP, phone, "password_reset", channel="sms", hashed_password=None)
        db.commit()
        body = otp_response(code, contact=phone)
        body["message"] = generic["message"]
        return body

    @staticmethod
    def forgot_password_verify_otp(db: Session, phone: str, otp: str):
        row = consume_otp(db, USER_OTP, phone, "password_reset", otp)
        token = issue_reset_token(row)
        db.commit()
        return {"success": True, "message": "OTP verified", "reset_token": token}

    @staticmethod
    def reset_password(db: Session, phone: str, reset_token: str, new_password: str, confirm_password: str):
        if new_password != confirm_password:
            raise DomainError("New password and confirm password do not match")
        redeem_reset_token(db, USER_OTP, phone, reset_token)
        user = UserRepository.get_by_phone(db, phone)
        if user is None:
            raise DomainError("Password reset session is invalid or has expired. Please start again.")
        user.password_hash = hash_password(new_password)
        user.failed_login_count = 0
        user.locked_until = None
        revoke_sessions(user)
        db.commit()
        security_event("password_reset.completed", role="customer", user_id=user.user_id)
        return {"success": True, "message": "Password reset successfully. Please log in."}

    @staticmethod
    def change_password(db: Session, user_id: str, current_password: str, new_password: str):
        user = UserRepository.get_by_user_id(db, user_id)
        if not verify_password(current_password, user.password_hash):
            raise DomainError("Current password is incorrect")
        user.password_hash = hash_password(new_password)
        revoke_sessions(user)
        db.commit()
        return {"success": True, "message": "Password changed. Please log in again."}

    @staticmethod
    def logout_user(db: Session, user_id: str):
        user = UserRepository.get_by_user_id(db, user_id)
        if user:
            revoke_sessions(user)
            db.commit()
        return {"success": True, "message": "Logged out successfully"}
