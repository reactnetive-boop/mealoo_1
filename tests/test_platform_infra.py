"""Rate-limit stores, request ids, health checks and login back-off."""

import fakeredis
import pytest
from sqlalchemy.exc import OperationalError

from app.core import observability, rate_limit
from app.core.errors import DomainError
from app.models.user_model import User
from app.services import auth_common
from app.services.user_auth_service import UserAuthService
from tests import factories as f

U = "/api/v1/user/auth"


# ── rate limit stores ─────────────────────────────────────────

@pytest.fixture(params=["memory", "redis"])
def store(request):
    if request.param == "memory":
        return rate_limit.MemoryStore()
    return rate_limit.RedisStore(fakeredis.FakeRedis())


def test_store_sliding_window(store):
    assert store.hit("w", 2, 60) is None
    assert store.hit("w", 2, 60) is None
    retry = store.hit("w", 2, 60)
    assert retry is not None and 1 <= retry <= 60
    store.delete("w")
    assert store.hit("w", 2, 60) is None


def test_store_counters_and_blocks(store):
    assert store.incr("c", 60) == 1
    assert store.incr("c", 60) == 2
    assert store.blocked_for("b") == 0
    store.block("b", 120)
    assert 1 <= store.blocked_for("b") <= 120
    store.reset()
    assert store.incr("c", 60) == 1
    assert store.blocked_for("b") == 0


def test_redis_outage_falls_back_to_memory():
    class Broken:
        def __getattr__(self, name):
            raise ConnectionError("redis down")

    rate_limit.configure(rate_limit.RedisStore(Broken()))
    try:
        assert rate_limit.incr("fallback", 60) == 1
        assert rate_limit.incr("fallback", 60) == 2
    finally:
        rate_limit.configure(rate_limit.MemoryStore())
        rate_limit.configure()


def test_endpoint_throttle_returns_retry_after(client):
    for _ in range(10):
        client.post(f"{U}/generate-otp", json={"phone": "9876543211", "password": "Secret@123"})
    r = client.post(f"{U}/generate-otp", json={"phone": "9876543211", "password": "Secret@123"})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1


# ── request ids and health ────────────────────────────────────

def test_every_response_carries_a_request_id(client):
    r = client.get("/health/live")
    assert len(r.headers["x-request-id"]) == 32
    mine = client.get("/health/live", headers={"X-Request-ID": "support-ticket-1234"})
    assert mine.headers["x-request-id"] == "support-ticket-1234"
    # anything odd is replaced, never echoed
    odd = client.get("/health/live", headers={"X-Request-ID": "<script>"})
    assert odd.headers["x-request-id"] != "<script>"


def test_request_id_reaches_sync_endpoints_and_500_refs(app, client):
    seen = {}

    def probe():
        seen["rid"] = observability.current_request_id()
        raise RuntimeError("boom")

    app.add_api_route("/__probe", probe, methods=["GET"])
    try:
        r = client.get("/__probe", headers={"X-Request-ID": "probe-request-0001"})
    finally:
        app.router.routes[:] = [rt for rt in app.router.routes if getattr(rt, "path", None) != "/__probe"]
    assert seen["rid"] == "probe-request-0001"
    assert r.status_code == 500
    assert "probe-request-0001" in r.json()["detail"]
    assert "boom" not in r.text


def test_health_checks_database(client, monkeypatch):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"

    import app.main as main

    class DeadEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(main, "engine", DeadEngine())
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["database"] == "unavailable"


def test_json_log_format_includes_request_id():
    import logging

    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.request_id = "abc"
    record.status = 200
    body = observability.JsonFormatter().format(record)
    assert '"msg": "hello world"' in body and '"request_id": "abc"' in body and '"status": 200' in body


# ── login back-off ────────────────────────────────────────────

def _login_from(db, ip, phone, password):
    token = observability._client_ip.set(ip)
    try:
        return UserAuthService.login(db, phone, password)
    finally:
        observability._client_ip.reset(token)


def test_wrong_passwords_lock_the_attacker_ip_not_the_owner(db):
    user, _, _ = f.customer(db)
    for _ in range(5):
        with pytest.raises(DomainError) as err:
            _login_from(db, "203.0.113.9", user.phone, "Wrong@1234")
        assert err.value.status_code == 401

    with pytest.raises(DomainError) as err:
        _login_from(db, "203.0.113.9", user.phone, f.PASSWORD)
    assert err.value.code == "LOGIN_THROTTLED"
    assert int(err.value.headers["Retry-After"]) > 14 * 60

    # the owner on their own network still gets in, and that clears their counters
    assert _login_from(db, "198.51.100.7", user.phone, f.PASSWORD)["access_token"]


def test_back_off_doubles_with_each_further_failure(db):
    user, _, _ = f.customer(db)
    for _ in range(5):
        with pytest.raises(DomainError):
            _login_from(db, "203.0.113.9", user.phone, "Wrong@1234")
    fails_key, block_key = auth_common._throttle_keys("customer", user, "203.0.113.9")
    rate_limit.delete(block_key)  # pretend the first 15 minutes passed
    with pytest.raises(DomainError):
        _login_from(db, "203.0.113.9", user.phone, "Wrong@1234")
    assert rate_limit.blocked_for(block_key) > 15 * 60


def test_distributed_attack_still_locks_the_account(db, monkeypatch):
    monkeypatch.setattr(auth_common, "LOGIN_ACCOUNT_LOCK_THRESHOLD", 3)
    user, _, _ = f.customer(db)
    for n in range(3):
        with pytest.raises(DomainError):
            _login_from(db, f"203.0.113.{n}", user.phone, "Wrong@1234")
    with pytest.raises(DomainError) as err:
        _login_from(db, "198.51.100.7", user.phone, f.PASSWORD)
    assert err.value.code == "ACCOUNT_LOCKED"
    db.expire_all()
    assert db.query(User).filter(User.user_id == user.user_id).one().locked_until is not None


def test_change_password_rules(client, db):
    user, _, headers = f.customer(db)
    same = client.put(f"{U}/change-password", headers=headers,
                      json={"current_password": f.PASSWORD, "new_password": f.PASSWORD})
    assert same.status_code == 400
    ok = client.put(f"{U}/change-password", headers=headers,
                    json={"current_password": f.PASSWORD, "new_password": "Another@123"})
    assert ok.status_code == 200
    # every earlier token is now dead
    assert client.get("/api/v1/user/profile", headers=headers).status_code == 401
