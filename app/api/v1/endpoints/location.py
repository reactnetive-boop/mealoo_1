from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db

from app.schemas.location_schema import (
    VerifyPincodeRequest
)

from app.services.pincode_service import PincodeService


router = APIRouter()


@router.post("/verify-pincode")
async def verify_pincode(
    request: VerifyPincodeRequest,
    db: Session = Depends(get_db)
):

    return PincodeService.verify_pincode(
        db=db,
        request=request
    )