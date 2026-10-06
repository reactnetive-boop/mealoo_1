import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from passlib.context import CryptContext
import jwt

from app.core.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.core.clock import now_utc

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# Token "role" claim per principal type. Every guard checks it, so a token
# minted for one app can never be replayed against another app's endpoints.
ROLE_CUSTOMER = "customer"
ROLE_PROVIDER = "provider"
ROLE_DELIVERY = "delivery_boy"
ROLE_ADMIN = "admin"


def hash_password(password: str):

    return pwd_context.hash(password)


def verify_password(
    plain_password,
    hashed_password
):

    if not plain_password or not hashed_password:
        return False

    try:
        return pwd_context.verify(
            plain_password,
            hashed_password
        )
    except (ValueError, TypeError):
        # Malformed hash in the DB must read as "wrong password", not a 500
        return False


# A real bcrypt hash, used to spend the same time on unknown accounts so
# response timing does not reveal whether a mobile number is registered.
_DUMMY_HASH = pwd_context.hash("timing-equaliser-not-a-password")


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def create_access_token(
    data: dict,
    role: str | None = None,
    token_version: int = 0,
    expires_minutes: int | None = None,
):
    """
    Issue a signed JWT.

    `role` and `ver` are always embedded: the auth guards reject a token whose
    role does not match the endpoint, or whose version is older than the one
    stored on the account (logout / password change / deactivation bump it).
    """

    to_encode = data.copy()

    if role is None:
        role = to_encode.get("role") or ROLE_CUSTOMER

    if expires_minutes is None:
        expires_minutes = (
            ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES
            if role == ROLE_ADMIN
            else ACCESS_TOKEN_EXPIRE_MINUTES
        )

    issued_at = now_utc()

    to_encode.update(
        {
            # The admin role (super_admin / moderator) is kept separately as
            # "admin_role"; "role" always identifies the principal type.
            "role": role,
            "ver": int(token_version or 0),
            "iat": int(issued_at.timestamp()),
            "exp": issued_at + timedelta(minutes=expires_minutes),
            "jti": uuid.uuid4().hex,
        }
    )

    encoded_jwt = jwt.encode(
        to_encode,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )

    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Verify signature and algorithm, then expiry against the app clock
    (app.core.clock), the same clock that set `exp`. Raises jwt.PyJWTError.
    """
    payload = jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp"], "verify_exp": False, "verify_iat": False},
    )
    try:
        expires = int(payload["exp"])
    except (TypeError, ValueError):
        raise jwt.InvalidTokenError("invalid exp") from None
    if expires <= int(now_utc().timestamp()):
        raise jwt.ExpiredSignatureError("token expired")
    return payload


# ── One-time codes ─────────────────────────────────────────

def generate_numeric_code(length: int = 6) -> str:
    """Cryptographically random numeric code (OTP, delivery / pickup code)."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def _code_key() -> bytes:
    # Derived so the raw JWT secret is never used for two purposes.
    return hashlib.sha256(f"otp::{JWT_SECRET_KEY}".encode()).digest()


def hash_code(code: str) -> str:
    """Keyed hash for OTPs stored at rest (HMAC-SHA256, hex)."""
    return hmac.new(_code_key(), code.encode(), hashlib.sha256).hexdigest()


def verify_code(code: str, stored_hash: str | None) -> bool:
    if not code or not stored_hash:
        return False
    return hmac.compare_digest(hash_code(code), stored_hash)


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
