"""Authentication: registration, OTP, login lockout, reset, revocation, role binding."""

import time

import jwt

from app.core.security import create_access_token
from app.models.user_model import User
from app.models.user_otp_log_model import UserOTPLog
from app.models.provider_model import Provider
from tests import factories as f

U = "/api/v1/user/auth"
P = "/api/v1/auth"
D = "/api/v1/delivery/auth"


def _register_customer(client, phone="9876543210", password="Secret@123"):
    r = client.post(f"{U}/generate-otp", json={"phone": phone, "password": password})
    assert r.status_code == 200, r.text
    otp = r.json()["otp"]
    r = client.post(f"{U}/verify-otp", json={"phone": phone, "otp": otp})
    assert r.status_code == 200, r.text
    return r.json()


def test_customer_register_and_login(client):
    _register_customer(client)
    r = client.post(f"{U}/login", json={"phone": "9876543210", "password": "Secret@123"})
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


def test_reregistration_cannot_take_over_existing_account(client, db):
    _register_customer(client, password="Original@123")
    r = client.post(f"{U}/generate-otp", json={"phone": "9876543210", "password": "Attacker@123"})
    assert r.status_code == 409
    assert r.json()["code"] == "ALREADY_REGISTERED"
    # original password still works, attacker's does not
    assert client.post(f"{U}/login", json={"phone": "9876543210", "password": "Original@123"}).status_code == 200
    assert client.post(f"{U}/login", json={"phone": "9876543210", "password": "Attacker@123"}).status_code == 401


def test_provider_and_partner_reregistration_blocked(client, db):
    kitchen, _ = f.provider(db)
    r = client.post(f"{P}/generate-otp", json={"mobile_number": kitchen.mobile_number, "password": "Attacker@123"})
    assert r.status_code == 409
    boy, _ = f.delivery_boy(db)
    r = client.post(f"{D}/register", json={"mobile_number": boy.mobile_number, "password": "Attacker@123"})
    assert r.status_code == 409


def test_otp_is_hashed_and_attempt_limited(client, db):
    r = client.post(f"{U}/generate-otp", json={"phone": "9876500000", "password": "Secret@123"})
    otp = r.json()["otp"]
    row = db.query(UserOTPLog).order_by(UserOTPLog.created_at.desc()).first()
    assert row.otp_hash != otp and otp not in row.otp_hash  # stored as HMAC, not plaintext
    wrong = "000000" if otp != "000000" else "111111"
    for _ in range(5):
        assert client.post(f"{U}/verify-otp", json={"phone": "9876500000", "otp": wrong}).status_code == 400
    # even the right code is refused once the attempts are used up
    r = client.post(f"{U}/verify-otp", json={"phone": "9876500000", "otp": otp})
    assert r.status_code in (400, 429)
    assert db.query(User).filter(User.phone == "9876500000").first() is None


def test_login_lockout_and_generic_errors(client, db):
    _register_customer(client)
    unknown = client.post(f"{U}/login", json={"phone": "9000099999", "password": "Whatever@1"})
    wrong = client.post(f"{U}/login", json={"phone": "9876543210", "password": "Wrong@1234"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]  # no account enumeration
    for _ in range(4):
        client.post(f"{U}/login", json={"phone": "9876543210", "password": "Wrong@1234"})
    # locked now: even the right password is refused
    r = client.post(f"{U}/login", json={"phone": "9876543210", "password": "Secret@123"})
    assert r.status_code in (401, 423, 429)
    assert client.post(f"{U}/login", json={"phone": "9876543210", "password": "Secret@123"}).status_code != 200


def test_password_reset_needs_reset_token_and_revokes_sessions(client, db):
    _register_customer(client)
    token = client.post(f"{U}/login", json={"phone": "9876543210", "password": "Secret@123"}).json()["access_token"]
    hdr = f.auth(token)
    assert client.get("/api/v1/user/me/state", headers=hdr).status_code == 200

    otp = client.post(f"{U}/forgot-password/send-otp", json={"phone": "9876543210"}).json()["otp"]
    # without the token issued by verify-otp the reset is refused
    r = client.post(f"{U}/forgot-password/reset", json={
        "phone": "9876543210", "reset_token": "x" * 40, "new_password": "NewPass@123", "confirm_password": "NewPass@123",
    })
    assert r.status_code in (400, 401)
    reset_token = client.post(f"{U}/forgot-password/verify-otp", json={"phone": "9876543210", "otp": otp}).json()["reset_token"]
    r = client.post(f"{U}/forgot-password/reset", json={
        "phone": "9876543210", "reset_token": reset_token, "new_password": "NewPass@123", "confirm_password": "NewPass@123",
    })
    assert r.status_code == 200, r.text
    # the reset token is single use
    r = client.post(f"{U}/forgot-password/reset", json={
        "phone": "9876543210", "reset_token": reset_token, "new_password": "Other@1234", "confirm_password": "Other@1234",
    })
    assert r.status_code in (400, 401)
    # old sessions are revoked
    assert client.get("/api/v1/user/me/state", headers=hdr).status_code == 401
    assert client.post(f"{U}/login", json={"phone": "9876543210", "password": "NewPass@123"}).status_code == 200


def test_logout_revokes_token(client, db):
    user, _, hdr = f.customer(db)
    assert client.post(f"{U}/logout", headers=hdr).status_code == 200
    assert client.get("/api/v1/user/me/state", headers=hdr).status_code == 401


def test_role_confusion_rejected(client, db):
    user, _, user_hdr = f.customer(db)
    kitchen, kitchen_hdr = f.provider(db)
    # a customer token on kitchen / partner / admin endpoints
    assert client.get("/api/v1/provider/me/state", headers=user_hdr).status_code == 403
    assert client.get("/api/v1/delivery/me/state", headers=user_hdr).status_code == 403
    assert client.get("/api/v1/admin/dashboard", headers=user_hdr).status_code == 403
    # a kitchen token whose subject id happens to be a customer's id
    forged = create_access_token({"user_id": str(user.user_id), "provider_id": str(kitchen.provider_id)}, role="provider")
    assert client.get("/api/v1/user/me/state", headers=f.auth(forged)).status_code == 403


def test_forged_and_unsigned_tokens_rejected(client, db):
    user, _, _ = f.customer(db)
    bad_sig = jwt.encode({"user_id": str(user.user_id), "role": "customer", "ver": 0, "exp": int(time.time()) + 600},
                         "not-the-secret-key-not-the-secret-key", algorithm="HS256")
    assert client.get("/api/v1/user/me/state", headers=f.auth(bad_sig)).status_code == 401
    header = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0"  # {"alg":"none"}
    import base64
    import json
    payload = base64.urlsafe_b64encode(json.dumps(
        {"user_id": str(user.user_id), "role": "customer", "ver": 0}).encode()).decode().rstrip("=")
    assert client.get("/api/v1/user/me/state", headers=f.auth(f"{header}.{payload}.")).status_code == 401
    assert client.get("/api/v1/user/me/state").status_code in (401, 403)


def test_admin_role_comes_from_database(client, db):
    mod, mod_hdr = f.admin(db, role="moderator")
    # a moderator cannot reach super-admin actions even with a hand-made "super_admin" claim
    forged = create_access_token({"admin_id": str(mod.admin_user_id), "admin_role": "super_admin"}, role="admin")
    for hdr in (mod_hdr, f.auth(forged)):
        r = client.put("/api/v1/admin/pricing/sms_charge", headers=hdr, json={
            "calc_type": "fixed", "value": "5", "charge_basis": "per_order", "change_reason": "test change",
        })
        assert r.status_code == 403


def test_inactive_kitchen_blocked_and_pending_kitchen_limited(client, db):
    pending, hdr = f.provider(db, approved=False)
    r = client.get("/api/v1/provider/me/state", headers=hdr)
    assert r.json()["next_step"] == "awaiting_approval"
    assert client.get("/api/v1/provider/orders/subscription-orders", headers=hdr).status_code == 403
    db.query(Provider).filter(Provider.provider_id == pending.provider_id).update({"is_active": False})
    db.commit()
    assert client.get("/api/v1/provider/me/state", headers=hdr).json()["next_step"] == "account_inactive"
