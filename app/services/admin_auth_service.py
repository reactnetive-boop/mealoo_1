from sqlalchemy.orm import Session

from app.core import totp
from app.core.audit import record_audit, security_event
from app.core.config import ADMIN_2FA_REQUIRED
from app.core.clock import now_utc
from app.core.errors import DomainError
from app.core.observability import current_client_ip
from app.core.security import (
    verify_password,
    hash_password,
    burn_password_check,
    create_access_token,
    ROLE_ADMIN,
)
from app.models.admin_user_model import AdminUser
from app.services.auth_common import (
    assert_login_allowed,
    register_failed_login,
    register_successful_login,
    revoke_sessions,
)

INVALID = "Invalid email or password"


def _admin(db: Session, admin_id) -> AdminUser:
    admin = db.query(AdminUser).filter(AdminUser.admin_user_id == admin_id).with_for_update().first()
    if not admin:
        raise DomainError("Admin not found", 404)
    return admin


def _second_factor_ok(admin: AdminUser, code: str, allow_recovery: bool = True) -> bool:
    """An authenticator code (never reused) or, failing that, an unused recovery code (spent here)."""
    step = totp.verify(admin.totp_secret, code, admin.totp_last_step)
    if step is not None:
        admin.totp_last_step = step
        return True
    if not allow_recovery or not code:
        return False
    hashed = totp.hash_recovery_code(code)
    remaining = list(admin.totp_recovery_hashes or [])
    if hashed in remaining:
        remaining.remove(hashed)
        admin.totp_recovery_hashes = remaining
        security_event("admin.recovery_code_used", admin_id=admin.admin_user_id, left=len(remaining))
        return True
    return False


def _clear_2fa(admin: AdminUser) -> None:
    admin.totp_enabled = False
    admin.totp_secret = None
    admin.totp_confirmed_at = None
    admin.totp_last_step = None
    admin.totp_recovery_hashes = None


def _token(admin: AdminUser) -> str:
    return create_access_token(
        {"admin_id": str(admin.admin_user_id), "email": admin.email},
        role=ROLE_ADMIN,
        token_version=admin.token_version,
    )


class AdminAuthService:

    @staticmethod
    def login(db: Session, email: str, password: str, totp_code: str | None = None):
        ip = current_client_ip()
        admin = db.query(AdminUser).filter(AdminUser.email == (email or "").strip()).first()
        assert_login_allowed(ROLE_ADMIN, admin, ip)

        if not admin:
            burn_password_check(password)
            security_event("admin.login_failed", email_domain=(email or "").split("@")[-1])
            raise DomainError(INVALID, 401)

        if not verify_password(password, admin.password_hash):
            register_failed_login(db, ROLE_ADMIN, admin, admin.email, ip)
            security_event("admin.login_failed", admin_id=admin.admin_user_id)
            raise DomainError(INVALID, 401)

        if not admin.is_active:
            raise DomainError("Admin account is deactivated", 403)

        if admin.totp_enabled:
            if not totp_code:
                # the password was right; the panel now asks for the authenticator code
                raise DomainError("Enter the 6-digit code from your authenticator app", 401, code="TOTP_REQUIRED")
            if not _second_factor_ok(admin, totp_code):
                register_failed_login(db, ROLE_ADMIN, admin, admin.email, ip)
                security_event("admin.totp_failed", admin_id=admin.admin_user_id)
                raise DomainError("The authenticator code is not valid", 401, code="TOTP_INVALID")

        register_successful_login(ROLE_ADMIN, admin, ip)
        admin.last_login_at = now_utc()
        db.commit()
        security_event("admin.login", admin_id=admin.admin_user_id, role=admin.role, two_factor=admin.totp_enabled)

        return {
            "success": True,
            "message": "Login successful",
            "admin_id": admin.admin_user_id,
            "role": admin.role,
            "access_token": _token(admin),
            "token_type": "bearer",
            "two_factor_enabled": bool(admin.totp_enabled),
            # the panel sends admins without 2FA to the enrolment screen
            "must_enroll_2fa": ADMIN_2FA_REQUIRED and not admin.totp_enabled,
        }

    # ── Two-factor login ──────────────────────────────────

    @staticmethod
    def start_2fa_setup(db: Session, admin_id: str) -> dict:
        admin = _admin(db, admin_id)
        if admin.totp_enabled:
            raise DomainError("Two-factor login is already on. Turn it off first to move it to a new phone.", 409)
        secret = totp.new_secret()
        admin.totp_secret = secret
        db.commit()
        return {
            "success": True,
            "secret": secret,
            "otpauth_uri": totp.provisioning_uri(secret, admin.email),
            "message": "Scan the QR code with an authenticator app, then confirm with the code it shows.",
        }

    @staticmethod
    def confirm_2fa_setup(db: Session, admin_id: str, code: str, ip: str | None = None) -> dict:
        admin = _admin(db, admin_id)
        if admin.totp_enabled:
            raise DomainError("Two-factor login is already on", 409)
        step = totp.verify(admin.totp_secret, code)
        if step is None:
            raise DomainError("The code does not match. Check the phone's time and try the newest code.",
                              code="TOTP_INVALID")
        codes = totp.new_recovery_codes()
        admin.totp_enabled = True
        admin.totp_confirmed_at = now_utc()
        admin.totp_last_step = step
        admin.totp_recovery_hashes = [totp.hash_recovery_code(c) for c in codes]
        revoke_sessions(admin)  # every other session must log in again with the second factor
        record_audit(db, table="master.admin_users", record_id=admin.admin_user_id, new={"two_factor": "enabled"},
                     actor_id=admin.admin_user_id, actor_type="admin", ip=ip)
        db.commit()
        security_event("admin.totp_enabled", admin_id=admin.admin_user_id)
        return {
            "success": True,
            "message": "Two-factor login is on. Keep the recovery codes somewhere safe; each works once.",
            "recovery_codes": codes,
            "access_token": _token(admin),
            "token_type": "bearer",
        }

    @staticmethod
    def disable_2fa(db: Session, admin_id: str, password: str, code: str, ip: str | None = None) -> dict:
        admin = _admin(db, admin_id)
        if not admin.totp_enabled:
            raise DomainError("Two-factor login is not on")
        if not verify_password(password, admin.password_hash) or not _second_factor_ok(admin, code):
            security_event("admin.totp_disable_failed", admin_id=admin.admin_user_id)
            raise DomainError("Password or code is not correct", 400)
        _clear_2fa(admin)
        record_audit(db, table="master.admin_users", record_id=admin.admin_user_id, new={"two_factor": "disabled"},
                     actor_id=admin.admin_user_id, actor_type="admin", ip=ip)
        db.commit()
        security_event("admin.totp_disabled", admin_id=admin.admin_user_id)
        return {"success": True, "message": "Two-factor login is off"}

    @staticmethod
    def regenerate_recovery_codes(db: Session, admin_id: str, code: str) -> dict:
        admin = _admin(db, admin_id)
        if not admin.totp_enabled or not _second_factor_ok(admin, code, allow_recovery=False):
            raise DomainError("The authenticator code is not valid", 400, code="TOTP_INVALID")
        codes = totp.new_recovery_codes()
        admin.totp_recovery_hashes = [totp.hash_recovery_code(c) for c in codes]
        db.commit()
        return {"success": True, "recovery_codes": codes, "message": "Old recovery codes no longer work."}

    @staticmethod
    def reset_2fa(db: Session, target_admin_id: str, super_admin_id: str, ip: str | None = None) -> dict:
        """A super admin turns off another admin's 2FA (lost phone). They must enrol again."""
        if str(target_admin_id) == str(super_admin_id):
            raise DomainError("Use your own recovery code or turn two-factor off from your profile")
        admin = _admin(db, target_admin_id)
        _clear_2fa(admin)
        revoke_sessions(admin)
        record_audit(db, table="master.admin_users", record_id=admin.admin_user_id, new={"two_factor": "reset"},
                     actor_id=super_admin_id, actor_type="admin", ip=ip)
        db.commit()
        security_event("admin.totp_reset", admin_id=admin.admin_user_id, by=super_admin_id)
        return {"success": True, "message": f"Two-factor login reset for {admin.email}. They must enrol again."}

    @staticmethod
    def get_profile(db: Session, admin_id: str):
        admin = db.query(AdminUser).filter(AdminUser.admin_user_id == admin_id).first()
        if not admin:
            raise DomainError("Admin not found", 404)
        return {
            "success": True,
            "admin": {
                "admin_user_id": str(admin.admin_user_id),
                "full_name": admin.full_name,
                "email": admin.email,
                "role": admin.role,
                "is_active": admin.is_active,
                "two_factor_enabled": bool(admin.totp_enabled),
                "recovery_codes_left": len(admin.totp_recovery_hashes or []),
                "last_login_at": admin.last_login_at,
                "created_at": admin.created_at,
            },
        }

    @staticmethod
    def change_password(db: Session, admin_id: str, payload):
        admin = db.query(AdminUser).filter(AdminUser.admin_user_id == admin_id).first()
        if not admin:
            raise DomainError("Admin not found", 404)
        if not verify_password(payload.current_password, admin.password_hash):
            raise DomainError("Current password is incorrect", 400)
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
