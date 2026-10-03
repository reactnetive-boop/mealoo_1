from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import security_event
from app.core.clock import now_utc
from app.core.errors import DomainError
from app.core.security import (
    verify_password,
    hash_password,
    burn_password_check,
    create_access_token,
    ROLE_ADMIN,
)
from app.models.admin_user_model import AdminUser
from app.services.auth_common import (
    assert_not_locked,
    register_failed_login,
    register_successful_login,
    revoke_sessions,
)

INVALID = "Invalid email or password"


def _token(admin: AdminUser) -> str:
    return create_access_token(
        {"admin_id": str(admin.admin_user_id), "email": admin.email},
        role=ROLE_ADMIN,
        token_version=admin.token_version,
    )


class AdminAuthService:

    @staticmethod
    def login(db: Session, email: str, password: str):
        admin = db.query(AdminUser).filter(AdminUser.email == (email or "").strip()).first()
        assert_not_locked(admin)

        if not admin:
            burn_password_check(password)
            security_event("admin.login_failed", email_domain=(email or "").split("@")[-1])
            raise HTTPException(status_code=401, detail=INVALID)

        if not verify_password(password, admin.password_hash):
            register_failed_login(db, admin, admin.email)
            security_event("admin.login_failed", admin_id=admin.admin_user_id)
            raise HTTPException(status_code=401, detail=INVALID)

        if not admin.is_active:
            raise HTTPException(status_code=403, detail="Admin account is deactivated")

        register_successful_login(admin)
        admin.last_login_at = now_utc()
        db.commit()
        security_event("admin.login", admin_id=admin.admin_user_id, role=admin.role)

        return {
            "success": True,
            "message": "Login successful",
            "admin_id": admin.admin_user_id,
            "role": admin.role,
            "access_token": _token(admin),
            "token_type": "bearer"
        }

    @staticmethod
    def get_profile(db: Session, admin_id: str):
        admin = db.query(AdminUser).filter(AdminUser.admin_user_id == admin_id).first()
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        return {
            "success": True,
            "admin": {
                "admin_user_id": str(admin.admin_user_id),
                "full_name": admin.full_name,
                "email": admin.email,
                "role": admin.role,
                "is_active": admin.is_active,
                "last_login_at": admin.last_login_at,
                "created_at": admin.created_at,
            },
        }

    @staticmethod
    def change_password(db: Session, admin_id: str, payload):
        admin = db.query(AdminUser).filter(AdminUser.admin_user_id == admin_id).first()
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        if not verify_password(payload.current_password, admin.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        if payload.current_password == payload.new_password:
            raise DomainError("New password must be different from the current one")

        admin.password_hash = hash_password(payload.new_password)
        # Every other session (other browsers, a stolen token) ends now
        revoke_sessions(admin)
        db.commit()
        security_event("admin.password_changed", admin_id=admin.admin_user_id)

        return {
            "success": True,
            "message": "Password changed successfully",
            "access_token": _token(admin),
            "token_type": "bearer",
        }

    @staticmethod
    def logout_admin(db: Session, admin_id: str):
        admin = db.query(AdminUser).filter(AdminUser.admin_user_id == admin_id).first()
        if admin:
            revoke_sessions(admin)
            db.commit()
        return {"success": True, "message": "Logged out successfully"}
