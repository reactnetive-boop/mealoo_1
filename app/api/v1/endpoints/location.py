from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db

from app.schemas.location_schema import (
    VerifyPincodeRequest
)

from app.services.pincode_service import PincodeService


router = APIRouter()


@router.post(
    "/verify-pincode",
    summary="Check if a Pincode is Serviceable",
    description=(
        "**Verify whether Mealoo delivers to a given pincode before showing packages.**\n\n"
        "Returns `is_serviceable: true/false` and the city/state if serviceable. "
        "Use this on the onboarding location screen or when the user changes their delivery address.\n\n"
        "**No authentication required.**\n\n"
        "**When to call:** Before `GET /user/menu/packages` — if not serviceable, "
        "show a 'Not available in your area' message instead of the package listing.\n\n"
        "**Flow:** Enter pincode → `POST /location/verify-pincode` → if serviceable → "
        "`GET /user/menu/packages?pin_code=...`"
    )
)
async def verify_pincode(
    request: VerifyPincodeRequest,
    db: Session = Depends(get_db)
):

    return PincodeService.verify_pincode(
        db=db,
        request=request
    )
