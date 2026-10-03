"""
Authentication guards.

Every guard:
  1. verifies the JWT signature and expiry,
  2. checks the token's role claim matches the endpoint's audience (a
     customer token can never call kitchen / delivery / admin endpoints),
  3. loads the account from the database and checks the token version (so
     logout, password change and deactivation revoke old tokens) and the
     account status.

Guards return the token payload dict (ids keyed as before) for the
endpoints; authorization decisions never trust anything else the client
sends.
"""

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.audit import security_event
from app.core.database import get_db
from app.core.security import (
    decode_access_token,
    ROLE_CUSTOMER,
    ROLE_PROVIDER,
    ROLE_DELIVERY,
    ROLE_ADMIN,
)
from app.models.user_model import User
from app.models.provider_model import Provider
from app.models.delivery_boy_model import DeliveryBoy
from app.models.admin_user_model import AdminUser

security = HTTPBearer(auto_error=False)

_INVALID = HTTPException(
    status_code=401,
    detail="Invalid or expired session. Please log in again.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _forbidden(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": code, "message": message})


def _decode(credentials: HTTPAuthorizationCredentials | None, role: str, request: Request) -> dict:
    if credentials is None or not credentials.credentials:
        raise _INVALID
    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise _INVALID
    if payload.get("role") != role:
        security_event(
            "auth.wrong_audience",
            expected=role,
            got=payload.get("role"),
            path=request.url.path,
        )
        raise _forbidden("WRONG_ACCOUNT_TYPE", "This session cannot access this resource")
    return payload


def _check_version(payload: dict, account) -> None:
    if int(payload.get("ver", -1)) != int(account.token_version or 0):
        raise _INVALID


# ── Customers ─────────────────────────────────────────────────

def get_current_user(
    request: Request,
    credentials=Depends(security),
    db: Session = Depends(get_db),
):
    payload = _decode(credentials, ROLE_CUSTOMER, request)
    user = db.query(User).filter(User.user_id == payload.get("user_id")).first()
    if user is None or user.deleted_at is not None:
        raise _INVALID
    _check_version(payload, user)
    if user.status != "active":
        raise _forbidden("ACCOUNT_INACTIVE", f"Your account is {user.status}. Please contact support.")
    payload["user_id"] = str(user.user_id)
    return payload


# ── Kitchens ──────────────────────────────────────────────────

def _provider(request: Request, credentials, db: Session) -> tuple[dict, Provider]:
    payload = _decode(credentials, ROLE_PROVIDER, request)
    provider = db.query(Provider).filter(Provider.provider_id == payload.get("provider_id")).first()
    if provider is None:
        raise _INVALID
    _check_version(payload, provider)
    payload["provider_id"] = str(provider.provider_id)
    return payload, provider


def get_provider_session(
    request: Request,
    credentials=Depends(security),
    db: Session = Depends(get_db),
):
    """Any logged-in kitchen, whatever its status (state, profile, onboarding)."""
    payload, _ = _provider(request, credentials, db)
    return payload


def get_active_provider(
    request: Request,
    credentials=Depends(security),
    db: Session = Depends(get_db),
):
    payload, provider = _provider(request, credentials, db)
    if not provider.is_active:
        raise _forbidden("ACCOUNT_INACTIVE", "Your kitchen account is inactive. Please contact support.")
    return payload


def get_current_provider(
    request: Request,
    credentials=Depends(security),
    db: Session = Depends(get_db),
):
    """An active, admin-approved kitchen (packages, orders, earnings)."""
    payload, provider = _provider(request, credentials, db)
    if not provider.is_active:
        raise _forbidden("ACCOUNT_INACTIVE", "Your kitchen account is inactive. Please contact support.")
    if not provider.is_profile_completed:
        raise _forbidden("PROFILE_INCOMPLETE", "Please complete your kitchen profile first.")
    if provider.approval_status != "approved":
        raise _forbidden("APPROVAL_PENDING", "Your kitchen is waiting for Orleeno approval.")
    return payload


# ── Delivery partners ─────────────────────────────────────────

def _delivery(request: Request, credentials, db: Session) -> tuple[dict, DeliveryBoy]:
    payload = _decode(credentials, ROLE_DELIVERY, request)
    boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == payload.get("delivery_boy_id")).first()
    if boy is None:
        raise _INVALID
    _check_version(payload, boy)
    payload["delivery_boy_id"] = str(boy.delivery_boy_id)
    return payload, boy


def get_delivery_session(
    request: Request,
    credentials=Depends(security),
    db: Session = Depends(get_db),
):
    """Any logged-in partner (state, onboarding, documents, notifications)."""
    payload, _ = _delivery(request, credentials, db)
    return payload


def get_active_delivery_boy(
    request: Request,
    credentials=Depends(security),
    db: Session = Depends(get_db),
):
    payload, boy = _delivery(request, credentials, db)
    if not boy.is_active:
        raise _forbidden("ACCOUNT_INACTIVE", "Your account is deactivated. Please contact support.")
    return payload


def get_current_delivery_boy(
    request: Request,
    credentials=Depends(security),
    db: Session = Depends(get_db),
):
    """An active, admin-approved partner (assigned orders, pickup, delivery)."""
    payload, boy = _delivery(request, credentials, db)
    if not boy.is_active:
        raise _forbidden("ACCOUNT_INACTIVE", "Your account is deactivated. Please contact support.")
    if boy.approval_status != "approved":
        raise _forbidden("APPROVAL_PENDING", "Your application is still under review.")
    return payload


# ── Admins ────────────────────────────────────────────────────

def get_current_admin(
    request: Request,
    credentials=Depends(security),
    db: Session = Depends(get_db),
):
    payload = _decode(credentials, ROLE_ADMIN, request)
    admin = db.query(AdminUser).filter(AdminUser.admin_user_id == payload.get("admin_id")).first()
    if admin is None:
        raise _INVALID
    _check_version(payload, admin)
    if not admin.is_active:
        raise _forbidden("ACCOUNT_INACTIVE", "Admin account is deactivated")
    # The admin role always comes from the database, never from the token
    return {
        "admin_id": str(admin.admin_user_id),
        "email": admin.email,
        "role": admin.role,
    }


def require_super_admin(
    request: Request,
    current=Depends(get_current_admin)
):

    if current.get("role") != "super_admin":
        security_event("auth.super_admin_required", admin_id=current.get("admin_id"), path=request.url.path)
        raise HTTPException(
            status_code=403,
            detail="super_admin role required"
        )

    return current
