"""
Write real API responses for the admin panel's tests.

Seeds the TEST database (refuses anything not ending in _test) with one of
everything through the normal factories and endpoints, calls every admin GET
endpoint, and saves the JSON bodies to
mealoo_admin/src/test/fixtures/api.json, keyed by URL path. The admin page
tests serve these, so they also check that the panel understands the real
response shapes.

    python scripts/dump_admin_fixtures.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from tests import conftest  # noqa: E402  (sets the test env and refuses non-_test databases)

from sqlalchemy import text  # noqa: E402

from app.core import clock  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.domain import ledger  # noqa: E402
from tests import factories as f  # noqa: E402

OUT = ROOT.parent / "mealoo_admin" / "src" / "test" / "fixtures" / "api.json"
A = "/api/v1/admin"


def main() -> None:
    import subprocess

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=os.environ.copy(),
                   check=True, capture_output=True)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(conftest._tables(conn)) + " RESTART IDENTITY CASCADE"))
        conn.execute(text(conftest.PRICING_DEFAULTS))
    clock.freeze(datetime(2026, 10, 5, 5, 0))

    from fastapi.testclient import TestClient

    from app.core.database import SessionLocal
    from app.main import app

    db = SessionLocal()
    client = TestClient(app)
    w = f.world(db, balance="5000")
    _, admin = f.admin(db)
    boy, boy_hdr = f.delivery_boy(db, kitchen=w["kitchen"])

    sub_id = client.post("/api/v1/user/subscription", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    }).json()["subscription_id"]
    client.put(f"{A}/orders/subscriptions/{sub_id}/assign-delivery-boy", headers=admin,
               json={"delivery_boy_id": str(boy.delivery_boy_id)})
    client.post("/api/v1/user/order/extra", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "address_id": str(w["address"].user_address_id),
        "delivery_date": "2026-10-06", "meal_slot": "lunch",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    client.post("/api/v1/user/wallet/recharge", headers=w["user_auth"], json={"amount": "200"})
    body = {"against": "platform", "subject": "App problem", "description": "Something is not working right."}
    client.post("/api/v1/user/complaint", headers=w["user_auth"], json=body)
    client.post("/api/v1/provider/complaint", headers=w["kitchen_auth"], json=body)
    client.post("/api/v1/delivery/complaint", headers=boy_hdr, json=body)
    client.put(f"/api/v1/menu/update/{w['package'].package_id}", headers=w["kitchen_auth"],
               json={"price": "190", "description": "Now with salad"})
    ledger.post_provider(db, w["kitchen"].provider_id, type="credit", amount="500", reason="adjustment",
                         idempotency_key="fixture:kitchen")
    db.commit()
    client.post("/api/v1/provider/wallet/withdraw", headers=w["kitchen_auth"], json={"amount": "300"})
    client.post(f"{A}/delivery-boys/{boy.delivery_boy_id}/leaves", headers=admin, json={"leave_date": "2026-10-09"})
    client.post(f"{A}/categories", headers=admin, json={"category_name": "South Indian"})
    f.pincode(db, 560002)
    client.post(f"{A}/providers/{w['kitchen'].provider_id}/service-areas", headers=admin, json={"pincode": 560002})

    pid, uid, bid = str(w["kitchen"].provider_id), str(w["user"].user_id), str(boy.delivery_boy_id)
    pkg = str(w["package"].package_id)
    plan = str(w["plan"].subscription_plan_id)
    complaints = client.get(f"{A}/complaints", headers=admin).json()["complaints"]
    user_complaint = next(c["id"] for c in complaints if c["complainant_type"] == "user")
    payment = client.get(f"{A}/payments", headers=admin).json()["payments"][0]["payment_id"]
    payout = client.get(f"{A}/payouts", headers=admin).json()["requests"][0]["payout_request_id"]

    paths = [
        "/auth/profile", "/dashboard", "/users", f"/users/{uid}", "/providers", f"/providers/{pid}",
        f"/providers/{pid}/unavailability", f"/providers/{pid}/service-areas", f"/providers/{pid}/payout-details",
        "/delivery-boys", f"/delivery-boys/{bid}", f"/delivery-boys/{bid}/leaves", "/packages", f"/packages/{pkg}",
        "/plans", f"/plans/{plan}", "/pincodes", "/categories", "/orders/subscription-orders",
        "/orders/extra-orders", "/orders/subscriptions", f"/orders/subscriptions/{sub_id}", "/complaints",
        f"/complaints/user/{user_complaint}", "/reviews", "/payments", f"/payments/{payment}", "/pricing",
        "/payouts", f"/payouts/{payout}/destination", "/audit-logs", "/audit-logs/tables", "/admins",
        "/maintenance/reconciliation",
    ]
    fixtures = {"ids": {"provider": pid, "user": uid, "delivery_boy": bid, "package": pkg, "plan": plan,
                        "subscription": sub_id, "complaint": user_complaint, "payment": payment, "payout": payout}}
    for path in paths:
        r = client.get(A + path, headers=admin)
        if r.status_code != 200:
            raise SystemExit(f"{path}: {r.status_code} {r.text[:300]}")
        fixtures[A + path] = r.json()
    for path in ("/api/v1/public/config", "/api/v1/menu/categories"):
        r = client.get(path, headers=admin)
        fixtures[path] = r.json()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixtures, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"wrote {len(fixtures) - 1} responses to {OUT}")
    db.close()


if __name__ == "__main__":
    main()
