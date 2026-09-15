from datetime import datetime
from datetime import timedelta,timezone

from sqlalchemy.orm import Session

from app.repositories.otp_repository import (
    OTPRepository
)

from app.utils.otp_generator import (
    generate_otp
)

from app.core.security import hash_password

from app.repositories.provider_repository import (
    ProviderRepository
)

from app.core.security import verify_password
from app.core.security import create_access_token

class AuthService:

    @staticmethod
    def generate_otp(
        db: Session,
        mobile_number: str,
        password: str
    ):

        otp = generate_otp()

        hashed_password = hash_password(
            password
        )

        otp_data = {

            "mobile_number": mobile_number,

            "otp": otp,

            "is_verified": False,

            "attempts": 0,

            "expires_at": (
                datetime.now(timezone.utc)
                + timedelta(minutes=15)
            ),

            "hashed_password": hashed_password,

            "purpose": "registration",
        }

        OTPRepository.create_otp(
            db,
            otp_data
        )

        # TEMPORARY
        # Later integrate SMS provider

        return {
            "success": True,
            "mobile_number": mobile_number,
            "message": "OTP generated successfully",
            "otp": otp
        }
    
    @staticmethod
    def verify_otp(
        db: Session,
        mobile_number: str,
        otp: str
    ):

        otp_record = (
            OTPRepository.get_latest_otp(
                db,
                mobile_number
            )
        )

        if not otp_record:

            raise Exception(
                "OTP not found"
            )

        if otp_record.is_verified:

            raise Exception(
                "OTP already used"
            )

        if datetime.now(timezone.utc) > otp_record.expires_at:

            raise Exception(
                "OTP expired"
            )

        if otp_record.otp != otp:

            otp_record.attempts += 1

            db.commit()

            raise Exception(
                "Invalid OTP"
            )

        otp_record.is_verified = True

        db.commit()

        provider = (
            ProviderRepository.get_by_mobile(
                db,
                mobile_number
            )
        )

        if provider:

            # A password-reset OTP only proves ownership of the number here;
            # the new password arrives later via /forgot-password/reset.
            if otp_record.purpose != "password_reset":

                provider.hashed_password = (
                    otp_record.hashed_password
                )

                db.commit()

            db.refresh(provider)

        else:

            provider_data = {

                "mobile_number": mobile_number,

                "hashed_password": (
                    otp_record.hashed_password
                ),

                "is_mobile_verified": True,

                "is_profile_completed": False
            }

            provider = (
                ProviderRepository.create_provider(
                    db,
                    provider_data
                )
            )

        return {
            "success": True,
            "message": "OTP verified successfully",
            "provider_id": str(
                provider.provider_id
            ),

            "is_profile_completed": (
                provider.is_profile_completed
            )
        }
    
    @staticmethod
    def forgot_password_send_otp(
        db: Session,
        mobile_number: str
    ):
        """
        Step 1 of password recovery. Unlike registration this takes no password —
        the provider has forgotten it — so the OTP row carries the provider's
        current hash. That keeps `hashed_password` populated and makes the shared
        `verify_otp` step a no-op re-assignment instead of a password change.
        """

        provider = (
            ProviderRepository.get_by_mobile(
                db,
                mobile_number
            )
        )

        if not provider:

            raise Exception(
                "Provider not found"
            )

        if not provider.is_active:

            raise Exception(
                "Provider account is inactive. Please contact support."
            )

        otp = generate_otp()

        otp_data = {

            "mobile_number": mobile_number,

            "otp": otp,

            "is_verified": False,

            "attempts": 0,

            "expires_at": (
                datetime.now(timezone.utc)
                + timedelta(minutes=15)
            ),

            "hashed_password": provider.hashed_password,

            "purpose": "password_reset",
        }

        OTPRepository.create_otp(
            db,
            otp_data
        )

        # TEMPORARY
        # Later integrate SMS provider

        return {
            "success": True,
            "mobile_number": mobile_number,
            "message": "OTP sent successfully",
            "otp": otp
        }

    @staticmethod
    def reset_password(
        db: Session,
        mobile_number: str,
        new_password: str,
        confirm_password: str
    ):
        """
        Step 3 of password recovery. Only callable while the most recent OTP for
        this mobile number is verified and still inside its validity window; the
        OTP is burnt afterwards so it cannot be replayed for a second reset.
        """

        if new_password != confirm_password:

            raise Exception(
                "New password and confirm password do not match"
            )

        provider = (
            ProviderRepository.get_by_mobile(
                db,
                mobile_number
            )
        )

        if not provider:

            raise Exception(
                "Provider not found"
            )

        otp_record = (
            OTPRepository.get_latest_otp(
                db,
                mobile_number,
                purpose="password_reset"
            )
        )

        if not otp_record or not otp_record.is_verified:

            raise Exception(
                "OTP not verified. Please verify the OTP before resetting the password."
            )

        if datetime.now(timezone.utc) > otp_record.expires_at:

            raise Exception(
                "OTP session expired. Please request a new OTP."
            )

        hashed_password = hash_password(
            new_password
        )

        provider.hashed_password = hashed_password

        # Burn the OTP: expiring it blocks both a replayed reset and a
        # re-verification of the same code.
        otp_record.hashed_password = hashed_password
        otp_record.expires_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(provider)

        return {
            "success": True,
            "message": "Password reset successfully",
            "provider_id": str(
                provider.provider_id
            )
        }

    @staticmethod
    def login(
        db: Session,
        mobile_number: str,
        password: str
    ):

        provider = (
            ProviderRepository.get_by_mobile(
                db,
                mobile_number
            )
        )

        if not provider:

            raise Exception(
                "Provider not found"
            )

        is_password_valid = verify_password(
            password,
            provider.hashed_password
        )

        if not is_password_valid:

            raise Exception(
                "Invalid password"
            )

        access_token = create_access_token(
            {
                "provider_id": str(
                    provider.provider_id
                ),
                "mobile_number": provider.mobile_number
            }
        )

        return {
            "success": True,
            "message": "Login successful",
            "access_token": access_token,
            "token_type": "bearer",
            "provider_id": str(
                provider.provider_id
            )
        }

    @staticmethod
    async def logout_provider():

        return {
            "success": True,
            "message": "Logged out successfully"
        }