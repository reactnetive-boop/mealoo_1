"""
Upload storage.

Files are stored under UPLOAD_DIR (a persistent volume in production) and
referenced in the database by a relative path "uploads/<area>/<uuid>.<ext>".

Public areas (package photos, profile photos) are served as static files at
/uploads/<area>/...; private areas (delivery partner KYC documents) are never
mounted and are streamed only through authenticated endpoints.

Every upload is size-limited and its type is taken from the file's magic
bytes, not from the client's filename or Content-Type. The stored name is a
random UUID, so filenames can never carry paths or script extensions.
"""

import os
import uuid

from fastapi import UploadFile

from app.core.config import UPLOAD_DIR, MAX_UPLOAD_BYTES
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

BASE_DIR = os.path.realpath(UPLOAD_DIR)

for _area in PUBLIC_AREAS + PRIVATE_AREAS:
    os.makedirs(os.path.join(BASE_DIR, _area), exist_ok=True)


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


def save_upload(file: UploadFile, area: str, allowed: set[str]) -> str:
    if area not in PUBLIC_AREAS + PRIVATE_AREAS:
        raise ValueError("unknown upload area")

    data = _read_limited(file)
    kind = sniff(data[:16])
    if kind not in allowed:
        raise DomainError(
            "Unsupported file type. Allowed: " + ", ".join(sorted(t.upper() for t in allowed))
        )

    name = f"{uuid.uuid4().hex}.{kind}"
    physical = os.path.join(BASE_DIR, area, name)
    with open(physical, "xb") as out:
        out.write(data)

    return f"{URL_PREFIX}/{area}/{name}"


def resolve(stored_path: str | None) -> str | None:
    """Physical path of a stored file, or None if it would escape UPLOAD_DIR."""
    if not stored_path:
        return None
    rel = stored_path.replace("\\", "/")
    if rel.startswith(URL_PREFIX + "/"):
        rel = rel[len(URL_PREFIX) + 1:]
    candidate = os.path.realpath(os.path.join(BASE_DIR, rel))
    if os.path.commonpath([candidate, BASE_DIR]) != BASE_DIR or candidate == BASE_DIR:
        return None
    return candidate


def delete_upload(stored_path: str | None) -> None:
    physical = resolve(stored_path)
    if physical and os.path.isfile(physical):
        os.remove(physical)


def content_type_of(stored_path: str) -> str:
    ext = stored_path.rsplit(".", 1)[-1].lower()
    return CONTENT_TYPES.get("jpg" if ext == "jpeg" else ext, "application/octet-stream")


# Backwards-compatible helpers used by the services

def save_profile_image(file: UploadFile) -> str:
    return save_upload(file, PROVIDER_PROFILE_AREA, IMAGE_TYPES)


def save_user_profile_image(file: UploadFile) -> str:
    return save_upload(file, USER_PROFILE_AREA, IMAGE_TYPES)


def save_package_image(file: UploadFile) -> str:
    return save_upload(file, PACKAGE_AREA, IMAGE_TYPES)


def save_delivery_document(file: UploadFile) -> str:
    return save_upload(file, DELIVERY_DOCUMENT_AREA, DOCUMENT_TYPES)
