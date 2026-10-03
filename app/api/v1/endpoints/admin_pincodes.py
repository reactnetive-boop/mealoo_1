from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.services.admin_content_service import AdminPincodeService
from app.schemas.admin_schema import AdminCreatePincodeRequest, AdminUpdatePincodeRequest

router = APIRouter()


@router.get(
    "",
    summary="List Serviceable Pincodes",
    description="Active pincodes are where kitchens can operate and customers can order.",
)
def list_pincodes(
    is_active: Optional[bool] = Query(None),
    city: Optional[str] = Query(None, max_length=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPincodeService.list_pincodes(db, is_active=is_active, city=city)


@router.post("", summary="Add Serviceable Pincode", description="**super_admin**.")
def create_pincode(
    payload: AdminCreatePincodeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminPincodeService.create_pincode(db, payload, current["admin_id"], client_ip(request))


@router.put(
    "/{pincode_id}",
    summary="Update Pincode",
    description=(
        "`is_active=false` stops new subscriptions and orders in that area immediately; running subscriptions "
        "continue. **super_admin**."
    ),
)
def update_pincode(
    pincode_id: int,
    payload: AdminUpdatePincodeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminPincodeService.update_pincode(db, pincode_id, payload, current["admin_id"], client_ip(request))


@router.delete(
    "/{pincode_id}",
    summary="Delete Pincode",
    description="Refused while kitchens or running subscriptions use the pincode; deactivate it instead. **super_admin**.",
)
def delete_pincode(pincode_id: int, request: Request, db: Session = Depends(get_db), current=Depends(require_super_admin)):
    return AdminPincodeService.delete_pincode(db, pincode_id, current["admin_id"], client_ip(request))
