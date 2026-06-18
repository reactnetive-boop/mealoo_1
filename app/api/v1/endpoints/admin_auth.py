from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_auth_service import AdminAuthService
from app.schemas.admin_schema import (
    AdminLoginRequest, AdminLoginResponse,
    AdminProfileResponse, AdminChangePasswordRequest
)

router = APIRouter()


@router.post("/login", response_model=AdminLoginResponse)
def login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    return AdminAuthService.login(db, payload.email, payload.password)


@router.get("/profile", response_model=dict)
def get_profile(db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminAuthService.get_profile(db, current["admin_id"])


@router.put("/change-password")
def change_password(
    payload: AdminChangePasswordRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminAuthService.change_password(db, current["admin_id"], payload)
