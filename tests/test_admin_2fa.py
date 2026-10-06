"""BE-S4: admin two-factor login (TOTP) with recovery codes."""

from datetime import datetime

from app.core import clock, totp
from tests import factories as f

A = "/api/v1/admin/auth"


def _code(secret, offset=0):
    return totp.code_at(secret, totp.current_step() + offset)


def _enrol(client, hdr):
    setup = client.post(f"{A}/2fa/setup", headers=hdr).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    r = client.post(f"{A}/2fa/enable", headers=hdr, json={"code": _code(setup["secret"])})
    assert r.status_code == 200, r.text
    return setup["secret"], r.json()


def _login(client, admin, code=None):
    body = {"email": admin.email, "password": f.PASSWORD}
    if code is not None:
        body["totp_code"] = code
    return client.post(f"{A}/login", json=body)


def test_rfc6238_reference_vector():
    # RFC 6238 appendix B, SHA1, T = 59 s -> 94287082 (8 digits); our 6-digit code is its tail
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp.code_at(secret, 59 // 30) == "287082"


def test_enrolment_then_login_needs_the_code(client, db):
    admin, hdr = f.admin(db)
    secret, enabled = _enrol(client, hdr)
    assert len(enabled["recovery_codes"]) == 8
    # enrolment signs every other session out
    assert client.get(f"{A}/profile", headers=hdr).status_code == 401

    r = _login(client, admin)
    assert r.status_code == 401 and r.json()["code"] == "TOTP_REQUIRED"
    assert _login(client, admin, "000000" if _code(secret) != "000000" else "111111").json()["code"] == "TOTP_INVALID"

    clock.freeze(datetime(2026, 10, 5, 5, 1))  # next time step
    ok = _login(client, admin, _code(secret))
    assert ok.status_code == 200 and ok.json()["two_factor_enabled"] is True
    # the same code cannot be replayed
    assert _login(client, admin, _code(secret)).status_code == 401


def test_recovery_code_works_once(client, db):
    admin, hdr = f.admin(db)
    _, enabled = _enrol(client, hdr)
    code = enabled["recovery_codes"][0]
    assert _login(client, admin, code).status_code == 200
    assert _login(client, admin, code).status_code == 401
    profile = client.get(f"{A}/profile", headers={"Authorization": f"Bearer {_login(client, admin, enabled['recovery_codes'][1]).json()['access_token']}"}).json()
    assert profile["admin"]["recovery_codes_left"] == 6


def test_disable_needs_password_and_code(client, db):
    admin, hdr = f.admin(db)
    secret, enabled = _enrol(client, hdr)
    hdr = {"Authorization": f"Bearer {enabled['access_token']}"}
    clock.freeze(datetime(2026, 10, 5, 5, 2))
    assert client.post(f"{A}/2fa/disable", headers=hdr, json={"password": "wrong-pass", "code": _code(secret)}).status_code == 400
    assert client.post(f"{A}/2fa/disable", headers=hdr, json={"password": f.PASSWORD, "code": _code(secret)}).status_code == 200
    assert _login(client, admin).status_code == 200


def test_super_admin_can_reset_a_lost_phone(client, db):
    moderator, mod_hdr = f.admin(db, role="moderator")
    _enrol(client, mod_hdr)
    _, super_hdr = f.admin(db)
    assert client.post(f"{A}/2fa/reset/{moderator.admin_user_id}", headers=mod_hdr).status_code in (401, 403)
    r = client.post(f"{A}/2fa/reset/{moderator.admin_user_id}", headers=super_hdr)
    assert r.status_code == 200, r.text
    assert _login(client, moderator).status_code == 200


def test_secret_is_encrypted_at_rest(client, db):
    from sqlalchemy import text

    admin, hdr = f.admin(db)
    secret, _ = _enrol(client, hdr)
    raw = db.execute(text("SELECT totp_secret FROM master.admin_users WHERE admin_user_id = :i"),
                     {"i": admin.admin_user_id}).scalar()
    assert raw.startswith("enc:v1:") and secret not in raw
