"""
Test harness.

Runs against a dedicated PostgreSQL database (default `mealoo_test`, override
with TEST_DATABASE_URL). Every test starts from empty tables plus the default
pricing configuration. The tests refuse to run against a database whose name
does not end in `_test`, so the development / production data can never be
truncated by accident.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
_env = dotenv_values(ROOT / ".env")

TEST_DB_URL = os.getenv("TEST_DATABASE_URL") or (
    f"postgresql://{_env.get('DB_USER', 'postgres')}:{quote_plus(_env.get('DB_PASSWORD') or '')}"
    f"@{_env.get('DB_HOST', 'localhost')}:{_env.get('DB_PORT', '5432')}/mealoo_test"
)
if not TEST_DB_URL.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
    raise SystemExit("Refusing to run tests against a database whose name does not end in _test")

# Must be set before the app is imported
os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": TEST_DB_URL,
    "RUN_SCHEDULER": "false",
    "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
    "JWT_ALGORITHM": "HS256",
    "OTP_ECHO_IN_RESPONSE": "true",
    "WALLET_SELF_TOPUP_ENABLED": "true",
    "ENABLE_API_DOCS": "false",
    "UPLOAD_DIR": str(ROOT / "tests" / ".uploads"),
    "LOG_LEVEL": "WARNING",
})

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402


def pytest_sessionstart(session):
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT, env=os.environ.copy(), check=True, capture_output=True,
    )


from app.core import clock  # noqa: E402
from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.rate_limit import reset_all  # noqa: E402

SCHEMAS = ("auth", "provider", "master", "subscription", "delivery")

PRICING_DEFAULTS = """
INSERT INTO master.pricing_components
    (pricing_component_id, component_key, label, calc_type, value, applies_to,
     charge_basis, is_customer_facing, is_active, version, change_reason)
VALUES
    (gen_random_uuid(), 'sms_charge', 'SMS Charge', 'fixed', 0, 'all', 'per_order', TRUE, TRUE, 1, 'initial'),
    (gen_random_uuid(), 'payment_gateway_charge', 'Payment Gateway Charge', 'percentage', 0, 'all', 'per_order', TRUE, TRUE, 1, 'initial'),
    (gen_random_uuid(), 'packaging_charge', 'Packaging / Shipping', 'fixed', 0, 'all', 'per_unit', TRUE, TRUE, 1, 'initial'),
    (gen_random_uuid(), 'delivery_charge', 'Delivery Charge', 'fixed', 0, 'all', 'per_delivery', TRUE, TRUE, 1, 'initial'),
    (gen_random_uuid(), 'platform_commission', 'Orleeno Commission', 'percentage', 0, 'all', 'per_order', TRUE, TRUE, 1, 'initial'),
    (gen_random_uuid(), 'delivery_partner_payout', 'Delivery Partner Payout', 'fixed', 30, 'all', 'per_delivery', FALSE, TRUE, 1, 'initial')
"""

# Monday 5 Oct 2026, 05:00 IST: before every meal cut-off of the day
DEFAULT_NOW = datetime(2026, 10, 5, 5, 0)


def _tables(conn):
    rows = conn.execute(text(
        "SELECT schemaname, tablename FROM pg_tables WHERE schemaname = ANY(:s) "
        "AND tablename <> 'alembic_version' AND tablename NOT LIKE 'audit_logs_%'"
    ), {"s": list(SCHEMAS)}).all()
    return [f'"{s}"."{t}"' for s, t in rows]


@pytest.fixture(autouse=True)
def clean_db():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(_tables(conn)) + " RESTART IDENTITY CASCADE"))
        conn.execute(text(PRICING_DEFAULTS))
    reset_all()
    from app.services import admin_dashboard_service
    admin_dashboard_service._cache.clear()  # the 60 s dashboard cache must not leak between tests
    clock.freeze(DEFAULT_NOW)
    yield
    clock.freeze(None)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
