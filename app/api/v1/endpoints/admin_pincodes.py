from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_content_service import AdminPincodeService
from app.schemas.admin_schema import AdminCreatePincodeRequest, AdminUpdatePincodeRequest

router = APIRouter()


@router.get(
    "",
    summary="List Serviceable Pincodes",
    description=(
        "**Fetch all pincodes where Mealoo is active.**\n\n"
        "Filter by `is_active` and/or `city`. "
        "These pincodes are what `POST /location/verify-pincode` checks against.\n\n"
        "**When to call:** On the admin service area management screen."
    )
)
def list_pincodes(
    is_active: Optional[bool] = Query(None),
    city: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPincodeService.list_pincodes(db, is_active=is_active, city=city)


@router.post(
    "",
    summary="Add Serviceable Pincode",
    description=(
        "**Add a new pincode to the list of delivery-serviceable areas.**\n\n"
        "Required: `pincode`, `city`, `state`. Optional: `is_active` (defaults to true).\n\n"
        "Once added and active, users in this area can browse meal packages from local providers."
    )
)
def create_pincode(
    payload: AdminCreatePincodeRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPincodeService.create_pincode(db, payload)


@router.put(
    "/{pincode_id}",
    summary="Update Pincode",
    description=(
        "**Edit an existing pincode entry (city, state, or active status).**\n\n"
        "Set `is_active=false` to temporarily disable delivery in that area "
        "without permanently removing it."
    )
)
def update_pincode(
    pincode_id: int,
    payload: AdminUpdatePincodeRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPincodeService.update_pincode(db, pincode_id, payload)


@router.delete(
    "/{pincode_id}",
    summary="Delete Pincode",
    description=(
        "**Permanently remove a pincode from the serviceable areas list.**\n\n"
        "Users in this pincode will no longer see packages. "
        "Consider using `PUT /{pincode_id}` with `is_active=false` to disable without deleting."
    )
)
def delete_pincode(
    pincode_id: int,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPincodeService.delete_pincode(db, pincode_id)
