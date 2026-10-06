"""
Registration, login and password flows shared by the three mobile apps.

The kitchen, customer and delivery-partner apps all register with phone +
password + OTP, log in with phone + password, reset forgotten passwords with
an OTP and a one-time reset token, and sign out every session on a password
change. `AccountAuth` implements those flows once; a subclass per app says
where its accounts live and what the app needs back in the responses.
"""

from sqlalchemy.orm import Session

from app.core.audit import security_event
from app.core.errors import DomainError
from app.core.observability import current_client_ip
from app.core.sms import send_otp
from app.core.security import burn_password_check, create_access_token, hash_password, verify_password
from app.services.auth_common import (
    INVALID_CREDENTIALS,
    OtpTable,
    assert_login_allowed,
    consume_otp,
    issue_otp,
    issue_reset_token,
    otp_response,
    redeem_reset_token,
    register_failed_login,
    register_successful_login,
    revoke_sessions,
)

RESET_SENT = "If this number is registered, an OTP has been sent."
RESET_INVALID = "Password reset session is invalid or has expired. Please start again."


def _already_registered(message: str) -> DomainError:
    return DomainError(message, 409, code="ALREADY_REGISTERED")


class AccountAuth:

    role: str                       # token role, also the label in security logs
    otp: OtpTable
    password_field: str             # model column holding the password hash
    id_field: str                   # primary key attribute; also the response key
    contact_field = "contact"       # response key that echoes the phone number
    signs_in_on_register = True     # registration returns an access token
    reset_otp_password: str | None = None   # value for the OTP row's hashed_password on resets
    otp_extra: dict = {}

    # ── what each app supplies ──
    def find_by_phone(self, db: Session, phone: str):
        raise NotImplementedError

    def find_by_id(self, db: Session, account_id):
        raise NotImplementedError

    def create(self, db: Session, phone: str, password_hash: str, **fields):
        raise NotImplementedError

    def is_active(self, account) -> bool:
        raise NotImplementedError

    def inactive_message(self, account) -> str:
        return "Your account is inactive. Please contact support."

    def token_claims(self, account) -> dict:
        raise NotImplementedError

    def account_fields(self, account) -> dict:
        """Extra keys returned on register and login (profile state etc.)."""
        return {}

    def on_login(self, account) -> None:
        pass

    def on_logout(self, account) -> None:
        pass

    # ── shared flows ──
    def _id(self, account) -> str:
        return str(getattr(account, self.id_field))

    def token(self, account) -> str:
        return create_access_token(self.token_claims(account), role=self.role, token_version=account.token_version)

    def _signed_in(self, account, message: str) -> dict:
        return {
            "success": True,
            "message": message,
            self.id_field: self._id(account),
            "access_token": self.token(account),
            "token_type": "bearer",
            **self.account_fields(account),
        }

    def generate_otp(self, db: Session, phone: str, password: str) -> dict:
        """Registration step 1. An existing number can never be re-registered."""
        if self.find_by_phone(db, phone):
            raise _already_registered(
                "This mobile number is already registered. Please log in or use Forgot Password."
            )
        code = issue_otp(db, self.otp, phone, "registration", hashed_password=hash_password(password),
                         **self.otp_extra)
        db.commit()
        send_otp(phone, code, "registration")
        return otp_response(code, **{self.contact_field: phone})

    def verify_otp(self, db: Session, phone: str, otp: str, **fields) -> dict:
        """Registration step 2: creates the account. Never touches an existing one."""
        row = consume_otp(db, self.otp, phone, "registration", otp)
        if self.find_by_phone(db, phone):
            db.commit()
            raise _already_registered("This mobile number is already registered. Please log in.")

        account = self.create(db, phone, row.hashed_password, **fields)
        db.commit()
        if self.signs_in_on_register:
            return self._signed_in(account, "OTP verified successfully")
        return {
            "success": True,
            "message": "OTP verified successfully. You can now log in.",
            self.id_field: self._id(account),
            **self.account_fields(account),
        }

    def login(self, db: Session, phone: str, password: str) -> dict:
        ip = current_client_ip()
        account = self.find_by_phone(db, phone)
        assert_login_allowed(self.role, account, ip)

        stored_hash = getattr(account, self.password_field, None) if account is not None else None
        if not stored_hash:
            burn_password_check(password)
            security_event("login.failed", role=self.role, identity=phone[-4:], ip=ip)
            raise DomainError(INVALID_CREDENTIALS, 401)

        if not verify_password(password, stored_hash):
            register_failed_login(db, self.role, account, phone, ip)
            raise DomainError(INVALID_CREDENTIALS, 401)

        if not self.is_active(account):
            raise DomainError(self.inactive_message(account), 403, code="ACCOUNT_INACTIVE")

        register_successful_login(self.role, account, ip)
        self.on_login(account)
        db.commit()
        return self._signed_in(account, "Login successful")

    def forgot_password_send_otp(self, db: Session, phone: str) -> dict:
        """Same answer whether or not the number exists (no account enumeration)."""
        account = self.find_by_phone(db, phone)
        if account is None or not self.is_active(account):
            security_event("password_reset.unknown_or_inactive", role=self.role, identity=phone[-4:])
            return {"success": True, self.contact_field: phone, "message": RESET_SENT}

        code = issue_otp(db, self.otp, phone, "password_reset", hashed_password=self.reset_otp_password,
                         **self.otp_extra)
        db.commit()
        send_otp(phone, code, "password_reset")
        body = otp_response(code, **{self.contact_field: phone})
        body["message"] = RESET_SENT
        return body

    def forgot_password_verify_otp(self, db: Session, phone: str, otp: str) -> dict:
        row = consume_otp(db, self.otp, phone, "password_reset", otp)
        token = issue_reset_token(row)
        db.commit()
        return {"success": True, "message": "OTP verified", "reset_token": token}

    def reset_password(self, db: Session, phone: str, reset_token: str, new_password: str,
                       confirm_password: str) -> dict:
        if new_password != confirm_password:
            raise DomainError("New password and confirm password do not match")
        redeem_reset_token(db, self.otp, phone, reset_token)
        account = self.find_by_phone(db, phone)
        if account is None:
            raise DomainError(RESET_INVALID)

        setattr(account, self.password_field, hash_password(new_password))
        account.failed_login_count = 0
        account.locked_until = None
        revoke_sessions(account)
        db.commit()
        security_event("password_reset.completed", role=self.role, account_id=self._id(account))
        return {
            "success": True,
            "message": "Password reset successfully. Please log in.",
            self.id_field: self._id(account),
        }

    def change_password(self, db: Session, account_id, current_password: str, new_password: str) -> dict:
        account = self.find_by_id(db, account_id)
        if account is None:
            raise DomainError("Account not found", 404)
        if not verify_password(current_password, getattr(account, self.password_field) or ""):
            raise DomainError("Current password is incorrect")
        if current_password == new_password:
            raise DomainError("New password must be different from the current one")
        setattr(account, self.password_field, hash_password(new_password))
        revoke_sessions(account)
        db.commit()
        security_event("password.changed", role=self.role, account_id=self._id(account))
        return {"success": True, "message": "Password changed. Please log in again."}

    def logout(self, db: Session, account_id) -> dict:
        account = self.find_by_id(db, account_id)
        if account is not None:
            revoke_sessions(account)
            self.on_logout(account)
            db.commit()
        return {"success": True, "message": "Logged out successfully"}
