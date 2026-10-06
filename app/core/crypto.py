"""
Application-level encryption for sensitive columns (bank account numbers).

Values are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) and stored as
"enc:v1:<token>". The key is DATA_ENCRYPTION_KEY (a Fernet key); without it a
key is derived from JWT_SECRET_KEY, which is fine for development but means
rotating the JWT secret would make old values unreadable, so production
should set its own key. DATA_ENCRYPTION_OLD_KEYS (comma separated) keeps
values written under earlier keys readable after a rotation.

Rows written before encryption existed are plain text; they are read as-is.
Migration c9d0e1f2a3b4 encrypts them, and any value written later is
encrypted.
"""

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy.types import Text, TypeDecorator

from app.core.config import DATA_ENCRYPTION_KEY, DATA_ENCRYPTION_OLD_KEYS, IS_PRODUCTION, JWT_SECRET_KEY

logger = logging.getLogger("app.crypto")

PREFIX = "enc:v1:"


def _derived_key() -> bytes:
    raw = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=b"orleeno-data-encryption", info=b"column-encryption-v1",
    ).derive((JWT_SECRET_KEY or "").encode())
    return base64.urlsafe_b64encode(raw)


def _fernet() -> MultiFernet:
    if not DATA_ENCRYPTION_KEY and IS_PRODUCTION:
        logger.warning("DATA_ENCRYPTION_KEY is not set; bank details are encrypted with a key derived from JWT_SECRET_KEY")
    primary = DATA_ENCRYPTION_KEY.encode() if DATA_ENCRYPTION_KEY else _derived_key()
    keys = [Fernet(primary)] + [Fernet(k.strip().encode()) for k in DATA_ENCRYPTION_OLD_KEYS if k.strip()]
    return MultiFernet(keys)


_cipher = _fernet()


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def encrypt(value: str | None) -> str | None:
    if value is None or is_encrypted(value):
        return value
    return PREFIX + _cipher.encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    if not is_encrypted(value):
        return value  # legacy plain text
    try:
        return _cipher.decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        logger.error("could not decrypt a stored value (wrong DATA_ENCRYPTION_KEY?)")
        return None


FILE_MARKER = b"ORLEENO-ENC1:"


def seal_bytes(data: bytes) -> bytes:
    """Encrypt a private file (KYC document) before it is stored."""
    return FILE_MARKER + _cipher.encrypt(data)


def open_bytes(data: bytes | None) -> bytes | None:
    """Decrypt a stored private file; files stored before encryption are returned as-is."""
    if data is None or not data.startswith(FILE_MARKER):
        return data
    try:
        return _cipher.decrypt(data[len(FILE_MARKER):])
    except InvalidToken:
        logger.error("could not decrypt a stored file (wrong DATA_ENCRYPTION_KEY?)")
        return None


class EncryptedString(TypeDecorator):
    """A text column that is encrypted in the database and plain in Python."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt(value)

    def process_result_value(self, value, dialect):
        return decrypt(value)
