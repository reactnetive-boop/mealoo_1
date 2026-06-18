from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.delivery_boy_auth_service import DeliveryBoyAuthService
from app.schemas.delivery_boy_schema import (
    DeliveryBoyRegisterRequest,
    DeliveryBoyVerifyOTPRequest,
    DeliveryBoyLoginRequest,
    DeliveryBoyAuthResponse,
)

router = APIRouter()


@router.post("/register", response_model=DeliveryBoyAuthResponse)
def register(
    payload: DeliveryBoyRegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        return DeliveryBoyAuthService.generate_otp(
            db,
            payload.mobile_number,
            payload.password
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify-otp", response_model=DeliveryBoyAuthResponse)
def verify_otp(
    payload: DeliveryBoyVerifyOTPRequest,
    db: Session = Depends(get_db)
):
    return DeliveryBoyAuthService.verify_otp(db, payload.mobile_number, payload.otp)


@router.post("/login", response_model=DeliveryBoyAuthResponse)
def login(
    payload: DeliveryBoyLoginRequest,
    db: Session = Depends(get_db)
):
    return DeliveryBoyAuthService.login(db, payload.mobile_number, payload.password)
