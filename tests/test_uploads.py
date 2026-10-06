"""Uploads: images are re-encoded without metadata; storage backends are swappable."""

import io

import pytest
from PIL import Image

from app.core import storage
from app.core.errors import DomainError
from app.utils import file_helper
from tests import factories as f


def _jpeg_with_gps(size=(64, 48)) -> bytes:
    img = Image.new("RGB", size, (200, 120, 40))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"                      # Make
    exif[0x8825] = {1: "N", 2: (12.0, 58.0, 0.0)}    # GPS IFD: latitude
    out = io.BytesIO()
    img.save(out, "JPEG", exif=exif)
    return out.getvalue()


def _upload(client, hdr, pkg, data, name="photo.jpg", ctype="image/jpeg"):
    return client.post("/api/v1/package/image/upload", headers=hdr, params={"package_id": str(pkg.package_id)},
                       files={"file": (name, io.BytesIO(data), ctype)})


def _stored_images(db, pkg):
    from app.models.menu_package_image_model import MenuPackageImage as PackageImage
    db.expire_all()
    return db.query(PackageImage).filter(PackageImage.package_reference_id == pkg.package_id).all()


def test_uploaded_photo_loses_exif_and_gps(client, db):
    kitchen, hdr = f.provider(db)
    pkg = f.package(db, kitchen, f.category(db))
    raw = _jpeg_with_gps()
    assert Image.open(io.BytesIO(raw)).getexif()  # the original carries metadata
    r = _upload(client, hdr, pkg, raw)
    assert r.status_code == 200, r.text

    stored = file_helper.read_upload(_stored_images(db, pkg)[0].image_url)
    clean = Image.open(io.BytesIO(stored))
    assert clean.format == "JPEG"
    assert not clean.getexif()
    assert b"PhoneMaker" not in stored


def test_large_photo_is_scaled_down(monkeypatch):
    monkeypatch.setattr(file_helper, "MAX_IMAGE_DIMENSION", 32)
    out = file_helper.clean_image(_jpeg_with_gps((200, 100)), "jpg")
    assert max(Image.open(io.BytesIO(out)).size) == 32


def test_broken_or_oversized_images_are_refused(monkeypatch):
    with pytest.raises(DomainError):
        file_helper.clean_image(b"\xff\xd8\xff" + b"not really a jpeg" * 10, "jpg")
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(DomainError):
        file_helper.clean_image(_jpeg_with_gps((64, 48)), "jpg")


@pytest.mark.parametrize("path", [
    "uploads/package_images/../../.env", "uploads/unknown_area/x.jpg", "uploads/package_images/a.b.jpg",
    "uploads/package_images/x.exe", "uploads/delivery_boys/documents/sub/x.pdf",
])
def test_storage_keys_only_name_known_areas(path):
    assert file_helper.storage_key(path) is None


class FakeS3:
    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType, ServerSideEncryption, CacheControl):
        assert ServerSideEncryption == "AES256"
        self.objects[Key] = (Body, ContentType, CacheControl)

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise self.exceptions.NoSuchKey()
        return {"Body": io.BytesIO(self.objects[Key][0])}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://signed.example/{Params['Key']}?expires={ExpiresIn}"


@pytest.fixture
def s3():
    fake = FakeS3()
    previous = storage.storage
    storage.use(storage.S3Storage("orleeno-test", client=fake))
    yield fake
    storage.use(previous)


def test_s3_backend_stores_serves_and_deletes(client, db, s3):
    kitchen, hdr = f.provider(db)
    pkg = f.package(db, kitchen, f.category(db))
    assert _upload(client, hdr, pkg, _jpeg_with_gps()).status_code == 200
    path = _stored_images(db, pkg)[0].image_url
    key = file_helper.storage_key(path)
    body, ctype, cache = s3.objects[key]
    assert ctype == "image/jpeg" and "public" in cache
    assert file_helper.public_url(path) == f"https://signed.example/{key}?expires=3600"

    file_helper.delete_upload(path)
    assert key not in s3.objects
    assert file_helper.read_upload(path) is None


def test_s3_public_base_url_and_private_documents(s3):
    storage.use(storage.S3Storage("orleeno-test", client=s3, public_base_url="https://cdn.example/"))
    storage.storage.put("delivery_boys/documents/abc.pdf", b"%PDF-1.4", "application/pdf", public=False)
    assert "private" in s3.objects["delivery_boys/documents/abc.pdf"][2]
    # KYC files never get a public URL
    assert file_helper.public_url("uploads/delivery_boys/documents/abc.pdf") is None
    assert file_helper.public_url("uploads/package_images/abc.jpg") == "https://cdn.example/package_images/abc.jpg"


def test_kyc_documents_are_encrypted_at_rest(client, db, s3):
    boy, hdr = f.delivery_boy(db, documents=False)
    pdf = b"%PDF-1.4\n% KYC aadhaar 1234 5678 9012\n"
    r = client.post("/api/v1/delivery/documents", headers=hdr, data={"document_type": "aadhaar"},
                    files={"file": ("aadhaar.pdf", io.BytesIO(pdf), "application/pdf")})
    assert r.status_code == 200, r.text
    key = next(k for k in s3.objects if k.startswith("delivery_boys/documents/"))
    stored = s3.objects[key][0]
    assert b"1234 5678 9012" not in stored and stored.startswith(b"ORLEENO-ENC1")
    assert file_helper.read_upload(f"uploads/{key}") == pdf
