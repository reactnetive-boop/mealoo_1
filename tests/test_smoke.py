from tests import factories as f


def test_health_and_headers(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


def test_public_config(client):
    r = client.get("/api/v1/public/config")
    assert r.status_code == 200
    body = r.json()
    assert body["timezone"] == "Asia/Kolkata"
    assert body["business_date"] == "2026-10-05"


def test_factories_work(client, db):
    w = f.world(db)
    r = client.get("/api/v1/user/me/state", headers=w["user_auth"])
    assert r.status_code == 200, r.text
    assert r.json()["next_step"] == "browse"
    r = client.get("/api/v1/provider/me/state", headers=w["kitchen_auth"])
    assert r.status_code == 200, r.text
    assert r.json()["next_step"] == "dashboard"
