from sqlalchemy.orm import Session

from app.core.audit import security_event
from app.core.errors import DomainError
from app.core.security import (
    hash_password,
    verify_password,
    burn_password_check,
    create_access_token,
    ROLE_PROVIDER,
)
from app.models.otp_log_model import OTPLog
from app.repositories.provider_repository import ProviderRepository
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

PROVIDER_OTP = OtpTable(model=OTPLog, identity="mobile_number", code="otp", used="is_verified")


class AuthService:

    @staticmethod
    def generate_otp(db: Session, mobile_number: str, password: str):
        """Registration step 1. An existing number can never be re-registered."""

        if ProviderRepository.get_by_mobile(db, mobile_number):
            raise DomainError(
                "This mobile number is already registered. Please log in or use Forgot Password.",
                409,
                code="ALREADY_REGISTERED",
            )

        code = issue_otp(
            db, PROVIDER_OTP, mobile_number, "registration",
            hashed_password=hash_password(password),
        )
        db.commit()
        return otp_response(code, mobile_number=mobile_number)

    @staticmethod
    def verify_otp(db: Session, mobile_number: str, otp: str):
        """Registration step 2: creates the kitchen account. Never touches an existing one."""

        row = consume_otp(db, PROVIDER_OTP, mobile_number, "registration", otp)

        if ProviderRepository.get_by_mobile(db, mobile_number):
            db.commit()
            raise DomainError("This mobile number is already registered. Please log in.", 409, code="ALREADY_REGISTERED")

        provider = ProviderRepository.create_provider(db, {
            "mobile_number": mobile_number,
            "hashed_password": row.hashed_password,
            "is_mobile_verified": True,
            "is_profile_completed": False,
            "approval_status": "pending",
        })

        return {
            "success": True,
            "message": "OTP verified successfully. You can now log in.",
            "provider_id": str(provider.provider_id),
            "is_profile_completed": provider.is_profile_completed,
        }

    @staticmethod
    def forgot_password_send_otp(db: Session, mobile_number: str):
        """Same response whether or not the number exists (no account enumeration)."""

        provider = ProviderRepository.get_by_mobile(db, mobile_number)
        if provider is None or not provider.is_active:
            security_event("password_reset.unknown_or_inactive", identity=mobile_number[-4:])
            return {
                "success": True,
                "mobile_number": mobile_number,
                "message": "If this number is registered, an OTP has been sent.",
            }

        code = issue_otp(db, PROVIDER_OTP, mobile_number, "password_reset", hashed_password="")
        db.commit()
        body = otp_response(code, mobile_number=mobile_number)
        body["message"] = "If this number is registered, an OTP has been sent."
        return body

    @staticmethod
    def forgot_password_verify_otp(db: Session, mobile_number: str, otp: str):
        row = consume_otp(db, PROVIDER_OTP, mobile_number, "password_reset", otp)
        token = issue_reset_token(row)
        db.commit()
        return {"success": True, "message": "OTP verified", "reset_token": token}

    @staticmethod
    def reset_password(db: Session, mobile_number: str, reset_token: str, new_password: str, confirm_password: str):

        if new_password != confirm_password:
            raise DomainError("New password and confirm password do not match")

        redeem_reset_token(db, PROVIDER_OTP, mobile_number, reset_token)
        provider = ProviderRepository.get_by_mobile(db, mobile_number)
        if provider is None:
            raise DomainError("Password reset session is invalid or has expired. Please start again.")

        provider.hashed_password = hash_password(new_password)
        provider.failed_login_count = 0
        provider.locked_until = None
        revoke_sessions(provider)
        db.commit()
        security_event("password_reset.completed", role="provider", provider_id=provider.provider_id)

        return {
            "success": True,
            "message": "Password reset successfully",
            "provider_id": str(provider.provider_id),
        }

    @staticmethod
    def login(db: Session, mobile_number: str, password: str):

        provider = ProviderRepository.get_by_mobile(db, mobile_number)
        assert_not_locked(provider)

        if provider is None:
            burn_password_check(password)
            security_event("login.failed", role="provider", identity=mobile_number[-4:])
            raise DomainError(INVALID_CREDENTIALS, 401)

        if not verify_password(password, provider.hashed_password):
            register_failed_login(db, provider, mobile_number)
            raise DomainError(INVALID_CREDENTIALS, 401)

        if not provider.is_active:
            raise DomainError("Your kitchen account is inactive. Please contact support.", 403, code="ACCOUNT_INACTIVE")

        register_successful_login(provider)
        db.commit()

        access_token = create_access_token(
            {"provider_id": str(provider.provider_id), "mobile_number": provider.mobile_number},
            role=ROLE_PROVIDER,
            token_version=provider.token_version,
        )

        return {
            "success": True,
            "message": "Login successful",
            "access_token": access_token,
            "token_type": "bearer",
            "provider_id": str(provider.provider_id),
            "is_profile_completed": bool(provider.is_profile_completed),
            "approval_status": provider.approval_status,
        }

    @staticmethod
    def change_password(db: Session, provider_id: str, current_password: str, new_password: str):
        provider = ProviderRepository.get_by_provider_id(db, provider_id)
        if not verify_password(current_password, provider.hashed_password):
            raise DomainError("Current password is incorrect")
        provider.hashed_password = hash_password(new_password)
        revoke_sessions(provider)
        db.commit()
        return {"success": True, "message": "Password changed. Please log in again."}

    @staticmethod
    def logout_provider(db: Session, provider_id: str):
        provider = ProviderRepository.get_by_provider_id(db, provider_id)
        if provider:
            revoke_sessions(provider)
            db.commit()
        return {"success": True, "message": "Logged out successfully"}
