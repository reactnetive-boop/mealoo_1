from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.dependencies.provider_dependency import (
    get_db
)

from app.schemas.auth_schema import (
    GenerateOTPRequest,VerifyOTPRequest
)


from app.services.auth_service import (
    AuthService
)

from app.schemas.auth_schema import LoginRequest
from app.schemas.auth_schema import LogoutResponse


router = APIRouter()


@router.post("/generate-otp")
def generate_otp(
    request: GenerateOTPRequest,
    db: Session = Depends(get_db)
):

    try:

        return AuthService.generate_otp(
            db,
            request.mobile_number,
            request.password
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    
@router.post("/verify-otp")
def verify_otp(
    request: VerifyOTPRequest,
    db: Session = Depends(get_db)
):

    try:

        return AuthService.verify_otp(
            db,
            request.mobile_number,
            request.otp
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

@router.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):

    try:

        return AuthService.login(
            db,
            request.mobile_number,
            request.password
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

@router.post(
    "/logout",
    response_model=LogoutResponse
)
async def logout_provider():

    response = await AuthService.logout_provider()

    return response        