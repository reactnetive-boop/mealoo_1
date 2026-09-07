from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_auth_service import AdminAuthService
from app.schemas.admin_schema import (
    AdminLoginRequest, AdminLoginResponse,
    AdminProfileResponse, AdminChangePasswordRequest
)
from app.schemas.auth_schema import LogoutResponse

router = APIRouter()


@router.post(
    "/login",
    response_model=AdminLoginResponse,
    summary="Admin Login",
    description=(
        "**Login for admin users using email and password.**\n\n"
        "Returns a JWT `access_token`. Include this in all admin API calls as "
        "`Authorization: Bearer <token>`.\n\n"
        "**Admin roles:** `super_admin` has full access; `moderator` has limited access.\n\n"
        "**After login:** Use `GET /admin/profile` to verify role and permissions."
    )
)
def login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    return AdminAuthService.login(db, payload.email, payload.password)


@router.get(
    "/profile",
    response_model=dict,
    summary="Get Admin Profile",
    description=(
        "**Fetch the logged-in admin's profile including role and permissions.**\n\n"
        "**When to call:** On admin panel load to determine which sections the admin can access "
        "based on their role (`super_admin` or `moderator`)."
    )
)
def get_profile(db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminAuthService.get_profile(db, current["admin_id"])


@router.put(
    "/change-password",
    summary="Change Admin Password",
    description=(
        "**Change the password for the currently logged-in admin account.**\n\n"
        "Send `current_password` and `new_password`. The session token remains valid after the change."
    )
)
def change_password(
    payload: AdminChangePasswordRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminAuthService.change_password(db, current["admin_id"], payload)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Admin Logout",
    description=(
        "**Invalidate the current admin session.**\n\n"
        "Call this when the admin logs out of the panel. "
        "The client should discard the stored token after this call."
    )
)
async def logout_admin():

    return await AdminAuthService.logout_admin()
