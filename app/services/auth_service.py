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