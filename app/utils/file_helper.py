"""
Uploads.

Files go to the configured storage backend (app.core.storage: a local
directory or an S3-compatible bucket) and are referenced in the database by
"uploads/<area>/<random>.<ext>".

Public areas (package photos, profile photos) are served at
/uploads/<area>/...; private areas (delivery partner KYC documents) are never
public and are streamed only through authenticated endpoints.

Every upload is size-limited and its type is taken from the file's magic
bytes, not from the client's filename or Content-Type. Images are decoded and
re-encoded: that drops EXIF / GPS and any other metadata, applies the camera
rotation, scales large photos down and guarantees the stored file really is
an image. The stored name is random, so filenames can never carry paths or
script extensions. Private files (KYC) are encrypted before they are stored.
"""

import io
import os
import re
import uuid
import warnings

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core import storage as _storage
from app.core.crypto import open_bytes, seal_bytes
from app.core.config import MAX_IMAGE_DIMENSION, MAX_UPLOAD_BYTES, UPLOAD_DIR
from app.core.errors import DomainError

URL_PREFIX = "uploads"

PACKAGE_AREA = "package_images"
PROVIDER_PROFILE_AREA = "providers/profile"
USER_PROFILE_AREA = "users/profile"
DELIVERY_DOCUMENT_AREA = "delivery_boys/documents"

PUBLIC_AREAS = (PACKAGE_AREA, PROVIDER_PROFILE_AREA, USER_PROFILE_AREA)
PRIVATE_AREAS = (DELIVERY_DOCUMENT_AREA,)

IMAGE_TYPES = {"jpg", "png", "webp"}
DOCUMENT_TYPES = IMAGE_TYPES | {"pdf"}

CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
}

# A 40 MP photo is plenty; anything bigger is refused before it is decoded
Image.MAX_IMAGE_PIXELS = 40_000_000

BASE_DIR = os.path.realpath(UPLOAD_DIR)
# one path segment, no dots before the extension: nothing can climb out of its area
_NAME = re.compile(r"[A-Za-z0-9_-]{1,100}\.(jpg|jpeg|png|webp|pdf)")

for _area in PUBLIC_AREAS + PRIVATE_AREAS:
    _storage.storage.ensure_area(_area)


def sniff(head: bytes) -> str | None:
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(b"%PDF-"):
        return "pdf"
    return None


def _read_limited(file: UploadFile) -> bytes:
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise DomainError(f"File is too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", 413)
    if not data:
        raise DomainError("The uploaded file is empty")
    return data


def clean_image(data: bytes, kind: str) -> bytes:
    """Decode and re-encode an image: no metadata, upright, at most MAX_IMAGE_DIMENSION px."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                source.load()
                img = ImageOps.exif_transpose(source)
        if max(img.size) > MAX_IMAGE_DIMENSION:
            img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
        out = io.BytesIO()
        if kind == "jpg":
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.save(out, "JPEG", quality=85, optimize=True, progressive=True)
        elif kind == "png":
            img.save(out, "PNG", optimize=True)
        else:
            img.save(out, "WEBP", quality=85)
        return out.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning,
            OSError, SyntaxError, ValueError):
        raise DomainError("The image could not be read. Please upload a JPG, PNG or WEBP photo.") from None


def save_upload(file: UploadFile, area: str, allowed: set[str]) -> str:
    if area not in PUBLIC_AREAS + PRIVATE_AREAS:
        raise ValueError("unknown upload area")

    data = _read_limited(file)
    kind = sniff(data[:16])
    if kind not in allowed:
        raise DomainError(
            "Unsupported file type. Allowed: " + ", ".join(sorted(t.upper() for t in allowed))
        )
    if kind in IMAGE_TYPES:
        data = clean_image(data, kind)

    key = f"{area}/{uuid.uuid4().hex}.{kind}"
    public = area in PUBLIC_AREAS
    if not public:
        data = seal_bytes(data)  # KYC documents are encrypted at rest on any backend
    _storage.storage.put(key, data, CONTENT_TYPES[kind], public=public)
    return f"{URL_PREFIX}/{key}"


def storage_key(stored_path: str | None) -> str | None:
    """The storage key of a stored path, or None unless it is exactly <known area>/<random name>."""
    if not stored_path:
        return None
    rel = stored_path.replace("\\", "/")
    if rel.startswith(URL_PREFIX + "/"):
        rel = rel[len(URL_PREFIX) + 1:]
    area, _, name = rel.rpartition("/")
    if area not in PUBLIC_AREAS + PRIVATE_AREAS or not _NAME.fullmatch(name):
        return None
    return rel


def resolve(stored_path: str | None) -> str | None:
    """Physical path of a locally stored file, or None if it would escape UPLOAD_DIR."""
    key = storage_key(stored_path)
    if key is None:
        return None
    candidate = os.path.realpath(os.path.join(BASE_DIR, key))
    if os.path.commonpath([candidate, BASE_DIR]) != BASE_DIR or candidate == BASE_DIR:
        return None
    return candidate


def read_upload(stored_path: str | None) -> bytes | None:
    key = storage_key(stored_path)
    if key is None:
        return None
    data = _storage.storage.get(key)
    return data if key.rpartition("/")[0] in PUBLIC_AREAS else open_bytes(data)


def delete_upload(stored_path: str | None) -> None:
    key = storage_key(stored_path)
    if key:
        _storage.storage.delete(key)


def public_url(stored_path: str | None) -> str | None:
    """Where a public image can be fetched from (None for the local backend: same path on this API)."""
    key = storage_key(stored_path)
    if key is None or key.rpartition("/")[0] not in PUBLIC_AREAS:
        return None
    return _storage.storage.public_url(key)


def content_type_of(stored_path: str) -> str:
    ext = stored_path.rsplit(".", 1)[-1].lower()
    return CONTENT_TYPES.get("jpg" if ext == "jpeg" else ext, "application/octet-stream")


# Helpers used by the services

def save_profile_image(file: UploadFile) -> str:
    return save_upload(file, PROVIDER_PROFILE_AREA, IMAGE_TYPES)


def save_user_profile_image(file: UploadFile) -> str:
    return save_upload(file, USER_PROFILE_AREA, IMAGE_TYPES)


def save_package_image(file: UploadFile) -> str:
    return save_upload(file, PACKAGE_AREA, IMAGE_TYPES)


def save_delivery_document(file: UploadFile) -> str:
    return save_upload(file, DELIVERY_DOCUMENT_AREA, DOCUMENT_TYPES)
