"""
OTP and login protections shared by the customer, kitchen and delivery apps.

OTPs: random 6 digits (secrets), stored as a keyed hash, valid
OTP_TTL_MINUTES, at most OTP_MAX_ATTEMPTS guesses, single use, resend
cool-down and hourly cap per number. Purposes are separate: a registration
OTP can never complete a password reset and vice versa.

Password reset: verifying a reset OTP returns a one-time reset token (stored
hashed, short-lived). The final reset call must present that token, so
knowing a phone number is never enough to change its password.

Login: per-account failure counter with a temporary lock, plus generic error
messages that do not reveal whether a number is registered.
"""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.audit import security_event
from app.core.clock import now_utc
from app.core.config import (
    OTP_TTL_MINUTES,
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_COOLDOWN_SECONDS,
    OTP_MAX_PER_HOUR,
    OTP_ECHO_IN_RESPONSE,
    PASSWORD_RESET_TOKEN_TTL_MINUTES,
    LOGIN_MAX_FAILED_ATTEMPTS,
    LOGIN_LOCKOUT_MINUTES,
)
from app.core.errors import DomainError
from app.core.security import (
    generate_numeric_code,
    hash_code,
    verify_code,
    generate_reset_token,
    hash_reset_token,
)

INVALID_CREDENTIALS = "Invalid mobile number or password"


@dataclass(frozen=True)
class OtpTable:
    model: type
    identity: str      # column holding phone / contact
    code: str          # column holding the code hash
    used: str          # boolean column marking consumption


def _q(db: Session, table: OtpTable, identity: str, purpose: str):
    m = table.model
    return db.query(m).filter(getattr(m, table.identity) == identity, m.purpose == purpose)


def issue_otp(db: Session, table: OtpTable, identity: str, purpose: str, **extra) -> str:
    """Create a new OTP row (previous ones for the purpose are invalidated)."""

    now = now_utc()
    m = table.model

    recent = _q(db, table, identity, purpose).filter(m.created_at >= now - timedelta(hours=1)).all()
    if len(recent) >= OTP_MAX_PER_HOUR:
        security_event("otp.hourly_cap", identity=identity[-4:], purpose=purpose)
        raise DomainError("Too many OTP requests. Please try again later.", 429)
    latest = max((r.created_at for r in recent if r.created_at), default=None)
    if latest and (now - latest).total_seconds() < OTP_RESEND_COOLDOWN_SECONDS:
        raise DomainError(f"Please wait {OTP_RESEND_COOLDOWN_SECONDS} seconds before requesting another OTP.", 429)

    # Only the newest OTP is ever valid
    for row in _q(db, table, identity, purpose).filter(getattr(m, table.used) == False).all():  # noqa: E712
        setattr(row, table.used, True)
        row.expires_at = now

    code = generate_numeric_code(6)
    row = m(
        **{table.identity: identity, table.code: hash_code(code)},
        purpose=purpose,
        attempts=0,
        expires_at=now + timedelta(minutes=OTP_TTL_MINUTES),
        created_at=now,
        **extra,
    )
    setattr(row, table.used, False)
    db.add(row)
    db.flush()
    return code


def consume_otp(db: Session, table: OtpTable, identity: str, purpose: str, code: str):
    """
    Verify and consume the latest OTP. Failed guesses are counted (and
    committed by the caller even when this raises), and the OTP dies after
    OTP_MAX_ATTEMPTS.
    """

    m = table.model
    row = _q(db, table, identity, purpose).order_by(m.created_at.desc()).with_for_update().first()
    now = now_utc()

    if row is None or getattr(row, table.used) or row.expires_at <= now:
        raise DomainError("OTP is invalid or has expired. Please request a new one.")

    if (row.attempts or 0) >= OTP_MAX_ATTEMPTS:
        raise DomainError("Too many incorrect attempts. Please request a new OTP.", 429)

    if not verify_code(code, getattr(row, table.code)):
        row.attempts = (row.attempts or 0) + 1
        if row.attempts >= OTP_MAX_ATTEMPTS:
            setattr(row, table.used, True)
            row.expires_at = now
        db.commit()
        security_event("otp.failed", identity=identity[-4:], purpose=purpose, attempts=row.attempts)
        raise DomainError("Incorrect OTP")

    setattr(row, table.used, True)
    if hasattr(row, "verified_at"):
        row.verified_at = now
    db.flush()
    return row


def issue_reset_token(row) -> str:
    token = generate_reset_token()
    row.reset_token_hash = hash_reset_token(token)
    row.reset_token_expires_at = now_utc() + timedelta(minutes=PASSWORD_RESET_TOKEN_TTL_MINUTES)
    return token


def redeem_reset_token(db: Session, table: OtpTable, identity: str, token: str):
    m = table.model
    row = (
        _q(db, table, identity, "password_reset")
        .filter(m.reset_token_hash == hash_reset_token(token or ""))
        .with_for_update()
        .first()
    )
    if row is None or row.reset_token_expires_at is None or row.reset_token_expires_at <= now_utc():
        security_event("password_reset.bad_token", identity=identity[-4:])
        raise DomainError("Password reset session is invalid or has expired. Please start again.")
    # single use
    row.reset_token_hash = None
    row.reset_token_expires_at = None
    return row


def otp_response(code: str, **fields) -> dict:
    body = {"success": True, "message": "OTP sent successfully", **fields}
    if OTP_ECHO_IN_RESPONSE:
        # Development only: no SMS gateway yet. Never enabled in production.
        body["otp"] = code
    return body


# ── Login lockout ─────────────────────────────────────────────

def assert_not_locked(account) -> None:
    if account is not None and account.locked_until and account.locked_until > now_utc():
        raise DomainError("Too many failed attempts. Please try again later.", 429, code="ACCOUNT_LOCKED")


def register_failed_login(db: Session, account, identity: str) -> None:
    account.failed_login_count = (account.failed_login_count or 0) + 1
    if account.failed_login_count >= LOGIN_MAX_FAILED_ATTEMPTS:
        account.locked_until = now_utc() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
        account.failed_login_count = 0
        security_event("login.locked", identity=identity[-4:])
    db.commit()
    security_event("login.failed", identity=identity[-4:])


def register_successful_login(account) -> None:
    account.failed_login_count = 0
    account.locked_until = None


def revoke_sessions(account) -> None:
    """Invalidate every token issued so far for this account."""
    account.token_version = (account.token_version or 0) + 1
