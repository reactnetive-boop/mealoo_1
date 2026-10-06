from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip, limit_by_ip
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.services.admin_auth_service import AdminAuthService
from app.schemas.admin_schema import (
    AdminLoginRequest, AdminLoginResponse,
    AdminChangePasswordRequest,
    AdminDisableTotpRequest,
    AdminTotpCodeRequest,
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
    ),
    dependencies=[Depends(limit_by_ip("admin_login", 10, 300))],
)
def login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    return AdminAuthService.login(db, payload.email, payload.password, payload.totp_code)


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
        "Send `current_password` and `new_password`. Every other session is signed out and a "
        "fresh `access_token` is returned for this one."
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
def logout_admin(db: Session = Depends(get_db), current=Depends(get_current_admin)):

    return AdminAuthService.logout_admin(db, current["admin_id"])


# ── Two-factor login ──────────────────────────────────────────

@router.post(
    "/2fa/setup",
    summary="Start Two-Factor Enrolment",
    description="Returns a secret and an `otpauth://` link to show as a QR code. Nothing changes until confirmed.",
    dependencies=[Depends(limit_by_ip("admin_2fa", 20, 300))],
)
def start_2fa(db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminAuthService.start_2fa_setup(db, current["admin_id"])


@router.post(
    "/2fa/enable",
    summary="Confirm Two-Factor Enrolment",
    description="Send the current code from the authenticator app. Returns one-time recovery codes (shown once) "
                "and a fresh token; every other session is signed out.",
    dependencies=[Depends(limit_by_ip("admin_2fa", 20, 300))],
)
def enable_2fa(payload: AdminTotpCodeRequest, request: Request, db: Session = Depends(get_db),
               current=Depends(get_current_admin)):
    return AdminAuthService.confirm_2fa_setup(db, current["admin_id"], payload.code, client_ip(request))


@router.post(
    "/2fa/disable",
    summary="Turn Off Two-Factor Login",
    description="Needs the password and a current code (or a recovery code).",
    dependencies=[Depends(limit_by_ip("admin_2fa", 20, 300))],
)
def disable_2fa(payload: AdminDisableTotpRequest, request: Request, db: Session = Depends(get_db),
                current=Depends(get_current_admin)):
    return AdminAuthService.disable_2fa(db, current["admin_id"], payload.password, payload.code, client_ip(request))


@router.post(
    "/2fa/recovery-codes",
    summary="New Recovery Codes",
    description="Needs a current authenticator code. The old recovery codes stop working.",
    dependencies=[Depends(limit_by_ip("admin_2fa", 20, 300))],
)
def new_recovery_codes(payload: AdminTotpCodeRequest, db: Session = Depends(get_db),
                       current=Depends(get_current_admin)):
    return AdminAuthService.regenerate_recovery_codes(db, current["admin_id"], payload.code)


@router.post(
    "/2fa/reset/{admin_id}",
    summary="Reset Another Admin's Two-Factor Login",
    description="For a lost phone: turns 2FA off for that admin and signs them out. Audited. **super_admin**.",
)
def reset_2fa(admin_id: UUID, request: Request, db: Session = Depends(get_db),
              current=Depends(require_super_admin)):
    return AdminAuthService.reset_2fa(db, str(admin_id), current["admin_id"], client_ip(request))
