from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.delivery_boy_repository import DeliveryBoyRepository
from app.core.security import hash_password, verify_password, create_access_token
from app.utils.otp_generator import generate_otp


class DeliveryBoyAuthService:

    @staticmethod
    def generate_otp(db: Session, mobile_number: str, password: str):
        otp = generate_otp()

        DeliveryBoyRepository.create_otp(db, {
            "mobile_number": mobile_number,
            "otp": otp,
            "hashed_password": hash_password(password),
            "is_verified": False,
            "attempts": 0,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
        })

        return {
            "success": True,
            "contact": mobile_number,
            "message": "OTP generated successfully",
            "otp": otp  # remove in production — send via SMS
        }

    @staticmethod
    def verify_otp(db: Session, mobile_number: str, otp: str):
        record = DeliveryBoyRepository.get_latest_otp(db, mobile_number)

        if not record:
            raise HTTPException(status_code=400, detail="OTP not found")
        if record.is_verified:
            raise HTTPException(status_code=400, detail="OTP already used")
        if datetime.now(timezone.utc) > record.expires_at:
            raise HTTPException(status_code=400, detail="OTP expired")
        if record.otp != otp:
            record.attempts += 1
            db.commit()
            raise HTTPException(status_code=400, detail="Invalid OTP")

        record.is_verified = True
        db.commit()

        boy = DeliveryBoyRepository.get_by_mobile(db, mobile_number)

        if boy:
            boy.hashed_password = record.hashed_password
            boy.is_mobile_verified = True
            db.commit()
            db.refresh(boy)
        else:
            boy = DeliveryBoyRepository.create(db, {
                "mobile_number": mobile_number,
                "hashed_password": record.hashed_password,
                "is_mobile_verified": True,
                "is_active": True,
            })

        access_token = create_access_token({
            "delivery_boy_id": str(boy.delivery_boy_id),
            "mobile_number": boy.mobile_number,
            "role": "delivery_boy"
        })

        is_profile_completed = bool(boy.full_name and boy.vehicle_type)

        return {
            "success": True,
            "message": "OTP verified successfully",
            "delivery_boy_id": str(boy.delivery_boy_id),
            "is_profile_completed": is_profile_completed,
            "access_token": access_token,
            "token_type": "bearer"
        }

    @staticmethod
    def login(db: Session, mobile_number: str, password: str):
        boy = DeliveryBoyRepository.get_by_mobile(db, mobile_number)

        if not boy:
            raise HTTPException(status_code=404, detail="Delivery boy not found")
        if not boy.is_mobile_verified:
            raise HTTPException(status_code=403, detail="Mobile number not verified")
        if not boy.is_active:
            raise HTTPException(status_code=403, detail="Account is deactivated")
        if not verify_password(password, boy.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid password")

        access_token = create_access_token({
            "delivery_boy_id": str(boy.delivery_boy_id),
            "mobile_number": boy.mobile_number,
            "role": "delivery_boy"
        })

        is_profile_completed = bool(boy.full_name and boy.vehicle_type)

        return {
            "success": True,
            "message": "Login successful",
            "delivery_boy_id": str(boy.delivery_boy_id),
            "is_profile_completed": is_profile_completed,
            "access_token": access_token,
            "token_type": "bearer"
        }

    @staticmethod
    async def logout_delivery_boy():

        return {
            "success": True,
            "message": "Logged out successfully"
        }
