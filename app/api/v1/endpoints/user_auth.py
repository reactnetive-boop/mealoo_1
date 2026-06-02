from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.dependencies.provider_dependency import get_db
from app.schemas.user_auth_schema import (
    UserGenerateOTPRequest,
    UserVerifyOTPRequest,
    UserLoginRequest
)
from app.services.user_auth_service import UserAuthService

router = APIRouter()


@router.post("/generate-otp")
def generate_otp(
    request: UserGenerateOTPRequest,
    db: Session = Depends(get_db)
):

    try:

        return UserAuthService.generate_otp(
            db,
            request.phone,
            request.email,
            request.password
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post("/verify-otp")
def verify_otp(
    request: UserVerifyOTPRequest,
    db: Session = Depends(get_db)
):

    try:

        return UserAuthService.verify_otp(
            db,
            request.phone,
            request.email,
            request.otp
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post("/login")
def login(
    request: UserLoginRequest,
    db: Session = Depends(get_db)
):

    try:

        return UserAuthService.login(
            db,
            request.phone,
            request.email,
            request.password
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
