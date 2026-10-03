from sqlalchemy.orm import Session

from app.core.audit import security_event
from app.core.errors import DomainError
from app.core.security import (
    hash_password,
    verify_password,
    burn_password_check,
    create_access_token,
    ROLE_DELIVERY,
)
from app.models.delivery_boy_otp_log_model import DeliveryBoyOTPLog
from app.repositories.delivery_boy_repository import DeliveryBoyRepository
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

DELIVERY_OTP = OtpTable(model=DeliveryBoyOTPLog, identity="mobile_number", code="otp", used="is_verified")


def _profile_completed(boy) -> bool:
    return bool(boy.full_name and boy.vehicle_type)


def _token(boy) -> str:
    return create_access_token(
        {"delivery_boy_id": str(boy.delivery_boy_id), "mobile_number": boy.mobile_number},
        role=ROLE_DELIVERY,
        token_version=boy.token_version,
    )


class DeliveryBoyAuthService:

    @staticmethod
    def generate_otp(db: Session, mobile_number: str, password: str):
        if DeliveryBoyRepository.get_by_mobile(db, mobile_number):
            raise DomainError(
                "This mobile number is already registered. Please log in or use Forgot Password.",
                409,
                code="ALREADY_REGISTERED",
            )
        code = issue_otp(
            db, DELIVERY_OTP, mobile_number, "registration",
            hashed_password=hash_password(password),
        )
        db.commit()
        return otp_response(code, contact=mobile_number)

    @staticmethod
    def verify_otp(db: Session, mobile_number: str, otp: str):
        """Creates the partner account (pending admin approval) and signs in."""

        row = consume_otp(db, DELIVERY_OTP, mobile_number, "registration", otp)

        if DeliveryBoyRepository.get_by_mobile(db, mobile_number):
            db.commit()
            raise DomainError("This mobile number is already registered. Please log in.", 409, code="ALREADY_REGISTERED")

        boy = DeliveryBoyRepository.create(db, {
            "mobile_number": mobile_number,
            "hashed_password": row.hashed_password,
            "is_mobile_verified": True,
            "is_active": True,
            "is_online": False,
            "approval_status": "pending",
        })

        return {
            "success": True,
            "message": "OTP verified successfully",
            "delivery_boy_id": str(boy.delivery_boy_id),
            "is_profile_completed": _profile_completed(boy),
            "access_token": _token(boy),
            "token_type": "bearer",
        }

    @staticmethod
    def login(db: Session, mobile_number: str, password: str):
        boy = DeliveryBoyRepository.get_by_mobile(db, mobile_number)
        assert_not_locked(boy)

        if boy is None:
            burn_password_check(password)
            security_event("login.failed", role="delivery_boy", identity=mobile_number[-4:])
            raise DomainError(INVALID_CREDENTIALS, 401)

        if not verify_password(password, boy.hashed_password):
            register_failed_login(db, boy, mobile_number)
            raise DomainError(INVALID_CREDENTIALS, 401)

        if not boy.is_active:
            raise DomainError("Account is deactivated. Please contact support.", 403, code="ACCOUNT_INACTIVE")

        register_successful_login(boy)
        db.commit()

        return {
            "success": True,
            "message": "Login successful",
            "delivery_boy_id": str(boy.delivery_boy_id),
            "is_profile_completed": _profile_completed(boy),
            "access_token": _token(boy),
            "token_type": "bearer",
        }

    @staticmethod
    def forgot_password_send_otp(db: Session, mobile_number: str):
        boy = DeliveryBoyRepository.get_by_mobile(db, mobile_number)
        generic = {"success": True, "contact": mobile_number, "message": "If this number is registered, an OTP has been sent."}
        if boy is None or not boy.is_active:
            security_event("password_reset.unknown_or_inactive", role="delivery_boy", identity=mobile_number[-4:])
            return generic
        code = issue_otp(db, DELIVERY_OTP, mobile_number, "password_reset", hashed_password="")
        db.commit()
        body = otp_response(code, contact=mobile_number)
        body["message"] = generic["message"]
        return body

    @staticmethod
    def forgot_password_verify_otp(db: Session, mobile_number: str, otp: str):
        row = consume_otp(db, DELIVERY_OTP, mobile_number, "password_reset", otp)
        token = issue_reset_token(row)
        db.commit()
        return {"success": True, "message": "OTP verified", "reset_token": token}

    @staticmethod
    def reset_password(db: Session, mobile_number: str, reset_token: str, new_password: str, confirm_password: str):
        if new_password != confirm_password:
            raise DomainError("New password and confirm password do not match")
        redeem_reset_token(db, DELIVERY_OTP, mobile_number, reset_token)
        boy = DeliveryBoyRepository.get_by_mobile(db, mobile_number)
        if boy is None:
            raise DomainError("Password reset session is invalid or has expired. Please start again.")
        boy.hashed_password = hash_password(new_password)
        boy.failed_login_count = 0
        boy.locked_until = None
        revoke_sessions(boy)
        db.commit()
        security_event("password_reset.completed", role="delivery_boy", delivery_boy_id=boy.delivery_boy_id)
        return {"success": True, "message": "Password reset successfully. Please log in."}

    @staticmethod
    def change_password(db: Session, delivery_boy_id: str, current_password: str, new_password: str):
        boy = DeliveryBoyRepository.get_by_id(db, delivery_boy_id)
        if not verify_password(current_password, boy.hashed_password):
            raise DomainError("Current password is incorrect")
        boy.hashed_password = hash_password(new_password)
        revoke_sessions(boy)
        db.commit()
        return {"success": True, "message": "Password changed. Please log in again."}

    @staticmethod
    def logout_delivery_boy(db: Session, delivery_boy_id: str):
        boy = DeliveryBoyRepository.get_by_id(db, delivery_boy_id)
        if boy:
            revoke_sessions(boy)
            boy.is_online = False
            db.commit()
        return {"success": True, "message": "Logged out successfully"}
