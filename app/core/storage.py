"""
Where uploaded files live.

  * local (default): a directory (UPLOAD_DIR). In production it must be a
    persistent volume, otherwise every deploy wipes the photos and KYC files.
  * s3: any S3-compatible bucket (AWS S3, Cloudflare R2, MinIO). Objects are
    written with server-side encryption. Public images are served from
    S3_PUBLIC_BASE_URL (a CDN or public bucket URL) when set, otherwise by a
    short-lived signed URL; private KYC files are only ever streamed through
    authenticated API endpoints.

Keys look like "<area>/<random>.<ext>"; the database keeps "uploads/<key>",
so stored paths stay the same whichever backend is used.
"""

import logging
import os

from app.core.config import (
    S3_ACCESS_KEY_ID,
    S3_BUCKET,
    S3_ENDPOINT_URL,
    S3_PUBLIC_BASE_URL,
    S3_REGION,
    S3_SECRET_ACCESS_KEY,
    STORAGE_BACKEND,
    UPLOAD_DIR,
)

logger = logging.getLogger("app.storage")

SIGNED_URL_SECONDS = 3600


class LocalStorage:
    name = "local"

    def __init__(self, root: str):
        self.root = os.path.realpath(root)

    def _path(self, key: str) -> str:
        return os.path.join(self.root, *key.split("/"))

    def ensure_area(self, area: str) -> None:
        os.makedirs(self._path(area), exist_ok=True)

    def put(self, key: str, data: bytes, content_type: str, public: bool) -> None:
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "xb") as out:  # names are random: never overwrite
            out.write(data)

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if os.path.isfile(path):
            os.remove(path)

    def public_url(self, key: str) -> str | None:
        return None  # served by the StaticFiles mount in app.main


class S3Storage:
    name = "s3"

    def __init__(self, bucket: str, *, client=None, public_base_url: str | None = None):
        self.bucket = bucket
        self.public_base_url = (public_base_url or "").rstrip("/") or None
        if client is None:
            import boto3  # optional dependency, only needed for this backend

            client = boto3.client(
                "s3",
                region_name=S3_REGION,
                endpoint_url=S3_ENDPOINT_URL,
                aws_access_key_id=S3_ACCESS_KEY_ID,
                aws_secret_access_key=S3_SECRET_ACCESS_KEY,
            )
        self.client = client

    def ensure_area(self, area: str) -> None:
        pass

    def put(self, key: str, data: bytes, content_type: str, public: bool) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
            CacheControl="public, max-age=31536000, immutable" if public else "private, no-store",
        )

    def get(self, key: str) -> bytes | None:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
        except self.client.exceptions.NoSuchKey:
            return None
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def public_url(self, key: str) -> str:
        if self.public_base_url:
            return f"{self.public_base_url}/{key}"
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=SIGNED_URL_SECONDS,
        )


def _default_storage():
    if STORAGE_BACKEND == "s3":
        return S3Storage(S3_BUCKET, public_base_url=S3_PUBLIC_BASE_URL)
    return LocalStorage(UPLOAD_DIR)


storage = _default_storage()


def use(backend) -> None:
    """Swap the backend (tests)."""
    global storage
    storage = backend
