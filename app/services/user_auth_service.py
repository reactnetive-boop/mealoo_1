from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.repositories.user_otp_repository import UserOTPRepository
from app.repositories.user_repository import UserRepository
from app.utils.otp_generator import generate_otp
from app.core.security import hash_password, verify_password, create_access_token


class UserAuthService:

    @staticmethod
    def generate_otp(
        db: Session,
        phone: str,
        email: str,
        password: str
    ):

        contact = phone if phone else email
        channel = "sms" if phone else "email"

        otp = generate_otp()

        otp_data = {
            "contact": contact,
            "channel": channel,
            "purpose": "registration",
            "otp_hash": hash_password(otp),
            "hashed_password": hash_password(password),
            "is_used": False,
            "attempts": 0,
            "expires_at": (
                datetime.now(timezone.utc)
                + timedelta(minutes=15)
            ),
        }

        UserOTPRepository.create_otp(db, otp_data)

        # TEMPORARY — integrate SMS/email provider later
        return {
            "success": True,
            "contact": contact,
            "message": "OTP generated successfully",
            "otp": otp
        }

    @staticmethod
    def verify_otp(
        db: Session,
        phone: str,
        email: str,
        otp: str
    ):

        contact = phone if phone else email

        otp_record = UserOTPRepository.get_latest_otp(
            db,
            contact,
            "registration"
        )

        if not otp_record:
            raise Exception("OTP not found")

        if otp_record.is_used:
            raise Exception("OTP already used")

        if datetime.now(timezone.utc) > otp_record.expires_at:
            raise Exception("OTP expired")

        if not verify_password(otp, otp_record.otp_hash):

            otp_record.attempts += 1

            db.commit()

            raise Exception("Invalid OTP")

        otp_record.is_used = True
        otp_record.verified_at = datetime.now(timezone.utc)

        db.commit()

        user = (
            UserRepository.get_by_phone(db, phone)
            if phone
            else UserRepository.get_by_email(db, email)
        )

        if user:

            if phone:
                user.phone_verified = True
            else:
                user.email_verified = True

            user.password_hash = otp_record.hashed_password

            db.commit()

            db.refresh(user)

        else:

            user_data = {
                "phone": phone if phone else None,
                "email": email if email else None,
                "phone_verified": bool(phone),
                "email_verified": bool(email),
                "password_hash": otp_record.hashed_password,
                "is_profile_completed": False,
                "status": "active"
            }

            user = UserRepository.create_user(db, user_data)

        access_token = create_access_token(
            {
                "user_id": str(user.user_id),
                "contact": contact
            }
        )

        return {
            "success": True,
            "message": "OTP verified successfully",
            "user_id": str(user.user_id),
            "is_profile_completed": user.is_profile_completed,
            "access_token": access_token,
            "token_type": "bearer"
        }

    @staticmethod
    def login(
        db: Session,
        phone: str,
        email: str,
        password: str
    ):

        user = (
            UserRepository.get_by_phone(db, phone)
            if phone
            else UserRepository.get_by_email(db, email)
        )

        if not user:
            raise Exception("User not found")

        if not user.password_hash:
            raise Exception(
                "Password not set. Please login via OTP."
            )

        if not verify_password(password, user.password_hash):
            raise Exception("Invalid password")

        user.last_login_at = datetime.now(timezone.utc)

        db.commit()

        contact = phone if phone else email

        access_token = create_access_token(
            {
                "user_id": str(user.user_id),
                "contact": contact
            }
        )

        return {
            "success": True,
            "message": "Login successful",
            "user_id": str(user.user_id),
            "access_token": access_token,
            "token_type": "bearer"
        }

    @staticmethod
    async def logout_user():

        return {
            "success": True,
            "message": "Logged out successfully"
        }
