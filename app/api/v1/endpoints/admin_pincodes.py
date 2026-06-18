from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_content_service import AdminPincodeService
from app.schemas.admin_schema import AdminCreatePincodeRequest, AdminUpdatePincodeRequest

router = APIRouter()


@router.get("")
def list_pincodes(
    is_active: Optional[bool] = Query(None),
    city: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPincodeService.list_pincodes(db, is_active=is_active, city=city)


@router.post("")
def create_pincode(
    payload: AdminCreatePincodeRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPincodeService.create_pincode(db, payload)


@router.put("/{pincode_id}")
def update_pincode(
    pincode_id: int,
    payload: AdminUpdatePincodeRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPincodeService.update_pincode(db, pincode_id, payload)


@router.delete("/{pincode_id}")
def delete_pincode(
    pincode_id: int,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPincodeService.delete_pincode(db, pincode_id)
