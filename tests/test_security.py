"""Uploads, private files, XSS payloads, mass assignment, IDOR on packages, error hygiene, rate limits."""

import io
import struct
import zlib

import pytest

from app.models.delivery_boy_document_model import DeliveryBoyDocument
from app.models.menu_package_model import MenuPackage
from app.models.user_model import User
from app.utils.file_helper import resolve
from tests import factories as f


def _png() -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"\x00\xff\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_upload_rejects_disguised_files_and_accepts_real_images(client, db):
    f.pincode(db)
    cat = f.category(db)
    kitchen, hdr = f.provider(db)
    pkg = f.package(db, kitchen, cat)
    html = b"<html><script>alert(1)</script></html>"
    r = client.post("/api/v1/package/image/upload", headers=hdr, params={"package_id": str(pkg.package_id)},
                    files={"file": ("evil.png", io.BytesIO(html), "image/png")})
    assert r.status_code in (400, 415, 422)
    r = client.post("/api/v1/package/image/upload", headers=hdr, params={"package_id": str(pkg.package_id)},
                    files={"file": ("photo.png", io.BytesIO(_png()), "image/png")})
    assert r.status_code == 200, r.text
    # stored under a random name, never the client's
    assert "photo.png" not in r.text


def test_other_kitchen_cannot_upload_to_or_edit_package(client, db):
    f.pincode(db)
    cat = f.category(db)
    owner, _ = f.provider(db)
    pkg = f.package(db, owner, cat)
    _, intruder = f.provider(db)
    r = client.post("/api/v1/package/image/upload", headers=intruder, params={"package_id": str(pkg.package_id)},
                    files={"file": ("p.png", io.BytesIO(_png()), "image/png")})
    assert r.status_code == 404
    assert client.put(f"/api/v1/menu/update/{pkg.package_id}", headers=intruder, json={"package_name": "Hacked"}).status_code == 404
    assert client.delete(f"/api/v1/menu/delete/{pkg.package_id}", headers=intruder).status_code == 404
    # no token at all
    assert client.put(f"/api/v1/menu/update/{pkg.package_id}", json={"package_name": "Hacked"}).status_code in (401, 403)


def test_kitchen_edit_cannot_self_approve(client, db):
    f.pincode(db)
    cat = f.category(db)
    kitchen, hdr = f.provider(db)
    pkg = f.package(db, kitchen, cat)
    r = client.put(f"/api/v1/menu/update/{pkg.package_id}", headers=hdr,
                   json={"price": "200", "approval_status": "approved", "provider_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code in (200, 422), r.text
    db.expire_all()
    row = db.query(MenuPackage).filter(MenuPackage.package_id == pkg.package_id).one()
    # the price change waits for review; the live price and ownership are untouched
    assert row.pending_changes["fields"] == {"price": "200"}
    assert row.price == 180 and row.approval_status == "approved"
    assert row.provider_id == kitchen.provider_id


def test_customer_profile_mass_assignment_ignored(client, db):
    user, _, hdr = f.customer(db)
    client.put("/api/v1/user/profile", headers=hdr, json={"full_name": "New Name", "status": "suspended", "phone_verified": False})
    db.expire_all()
    row = db.query(User).filter(User.user_id == user.user_id).one()
    assert row.status == "active" and row.phone_verified is True


def test_kyc_documents_are_not_public(client, db):
    boy, boy_hdr = f.delivery_boy(db)
    doc = db.query(DeliveryBoyDocument).first()
    assert client.get("/" + doc.file_url).status_code == 404
    _, other_hdr = f.delivery_boy(db)
    assert client.get(f"/api/v1/delivery/documents/{doc.delivery_boy_document_id}/file", headers=other_hdr).status_code == 404
    listing = client.get("/api/v1/delivery/documents", headers=boy_hdr).json()
    assert all(d["file_url"] is None for d in listing["documents"])


@pytest.mark.parametrize("path", ["../../etc/passwd", "uploads/../../app/main.py", "uploads/package_images/../../.env", "/etc/passwd"])
def test_path_traversal_resolves_to_nothing(path):
    assert resolve(path) is None


@pytest.mark.parametrize("url", ["javascript:alert(document.cookie)", "data:text/html,<script>x</script>",
                                 "http://insecure.example/x.png", "JaVaScRiPt:alert(1)"])
def test_complaint_evidence_rejects_script_urls(client, db, url):
    _, _, hdr = f.customer(db)
    r = client.post("/api/v1/user/complaint", headers=hdr, json={
        "against": "platform", "subject": "Broken app", "description": "The app keeps crashing on start.",
        "evidence_urls": [url],
    })
    assert r.status_code == 422


def test_validation_errors_do_not_echo_secrets(client):
    r = client.post("/api/v1/user/auth/login", json={"phone": "12", "password": "MySecretPassword!"})
    assert r.status_code == 422
    assert "MySecretPassword" not in r.text


def test_unexpected_errors_are_generic(app, db):
    from fastapi.testclient import TestClient
    from app.api.v1.api import api_router  # noqa: F401

    @app.get("/__boom")
    def boom():
        raise RuntimeError("db password=hunter2 at 10.0.0.5")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/__boom")
    assert r.status_code == 500
    assert "hunter2" not in r.text and "10.0.0.5" not in r.text
    assert "ref" in r.text.lower()


def test_otp_endpoints_are_rate_limited(client):
    codes = [client.post("/api/v1/user/auth/forgot-password/send-otp", json={"phone": "9876512345"}).status_code
             for _ in range(30)]
    assert 429 in codes


def test_docs_disabled_and_cors_restricted(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    r = client.options("/api/v1/public/config", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET",
    })
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"
    assert r.headers.get("access-control-allow-credentials") != "true"


def test_api_responses_not_cached(client):
    r = client.get("/api/v1/public/config")
    assert "no-store" in r.headers.get("cache-control", "")
