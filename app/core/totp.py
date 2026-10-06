"""
Time-based one-time passwords (RFC 6238, the codes Google Authenticator,
Microsoft Authenticator, Authy etc. show) for admin two-factor login.

30-second steps, 6 digits, HMAC-SHA1 (what every authenticator app expects);
one step of clock drift either way is accepted. Secrets are stored encrypted
(app.core.crypto); recovery codes are stored hashed and work once.
"""

import base64
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote

from app.core.clock import now_utc

STEP_SECONDS = 30
DIGITS = 6
DRIFT_STEPS = 1
ISSUER = "Orleeno Admin"


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def current_step() -> int:
    return int(now_utc().timestamp()) // STEP_SECONDS


def code_at(secret: str, step: int) -> str:
    return _code(secret, step)


def verify(secret: str | None, code: str | None, last_used_step: int | None = None) -> int | None:
    """The matching time step, or None. A step at or before `last_used_step` never matches (no replay)."""
    if not secret or not code:
        return None
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    now = current_step()
    for step in range(now - DRIFT_STEPS, now + DRIFT_STEPS + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if hmac.compare_digest(_code(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, account: str) -> str:
    """otpauth:// link (shown as a QR code by the admin panel)."""
    return (
        f"otpauth://totp/{quote(ISSUER)}:{quote(account)}"
        f"?secret={secret}&issuer={quote(ISSUER)}&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )


def new_recovery_codes(count: int = 8) -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()
