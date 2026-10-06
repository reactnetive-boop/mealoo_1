"""
Write real API responses for the customer app's tests.

Seeds the TEST database (refuses anything not ending in _test) through the
normal factories and endpoints, calls every customer GET endpoint the app
uses, and saves the JSON bodies to mealoo_user/src/__tests__/fixtures/api.json,
keyed by URL path (query strings dropped). The screen tests serve these through
a fake fetch, so they also check that the app understands the real shapes.

    python scripts/dump_customer_fixtures.py
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
from tests import factories as f  # noqa: E402

OUT = ROOT.parent / "mealoo_user" / "src" / "__tests__" / "fixtures" / "api.json"
U = "/api/v1/user"


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
    boy, _ = f.delivery_boy(db, kitchen=w["kitchen"])
    me = w["user_auth"]
    pid, pkg = str(w["kitchen"].provider_id), str(w["package"].package_id)

    sub_id = client.post(f"{U}/subscription", headers=me, json={
        "vendor_id": pid, "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": pkg, "quantity": 1}],
    }).json()["subscription_id"]
    client.put(f"/api/v1/admin/orders/subscriptions/{sub_id}/assign-delivery-boy", headers=admin,
               json={"delivery_boy_id": str(boy.delivery_boy_id)})
    placed = client.post(f"{U}/order/extra", headers=me, json={
        "vendor_id": pid, "address_id": str(w["address"].user_address_id),
        "delivery_date": "2026-10-06", "meal_slot": "lunch",
        "items": [{"package_id": pkg, "quantity": 2}],
    }).json()
    extra_id = placed["orders"][0]["extra_order_id"]
    client.post(f"{U}/wallet/recharge", headers=me, json={"amount": "200"})
    client.put(f"{U}/wallet/payout-details", headers=me, json={"upi_id": "ravi@okbank"})
    client.post(f"{U}/wallet/withdraw", headers=me, json={"amount": "100"})
    complaint_id = client.post(f"{U}/complaint", headers=me, json={
        "against": "platform", "subject": "App problem", "description": "Something is not working right.",
    }).json()["complaint_id"]
    client.post("/api/v1/admin/notifications/broadcast", headers=admin,
                json={"audience": "customers", "title": "Diwali menu", "body": "Special thalis this week"})

    pin = "560001"
    queries = {
        f"{U}/menu/packages": f"?pin_code={pin}",
        f"{U}/menu/serviceability": f"?pin_code={pin}",
        f"{U}/subscription/plans": "?subscription_type=weekly&meal_slot=lunch",
    }
    paths = [
        "/api/v1/public/config",
        f"{U}/profile", f"{U}/address", f"{U}/me/state",
        f"{U}/menu/packages", f"{U}/menu/serviceability", f"{U}/menu/packages/{pkg}",
        f"{U}/subscription", f"{U}/subscription/{sub_id}", f"{U}/subscription/{sub_id}/orders",
        f"{U}/subscription/plans/options", f"{U}/subscription/plans", f"{U}/subscription/packages",
        f"{U}/order/extra", f"{U}/order/extra/{extra_id}", f"{U}/order/today",
        f"{U}/wallet", f"{U}/wallet/transactions", f"{U}/wallet/payout-details", f"{U}/wallet/withdrawals",
        f"{U}/complaint", f"{U}/complaint/{complaint_id}",
        f"{U}/notification", f"{U}/review", f"{U}/review/vendor/{pid}",
    ]
    fixtures = {"ids": {"provider": pid, "package": pkg, "subscription": sub_id, "extra_order": extra_id,
                        "complaint": complaint_id, "address": str(w["address"].user_address_id),
                        "user": str(w["user"].user_id), "pin": pin}}
    for path in paths:
        r = client.get(path + queries.get(path, ""), headers=me)
        if r.status_code != 200:
            raise SystemExit(f"{path}: {r.status_code} {r.text[:300]}")
        fixtures[path] = r.json()

    # quotes the app asks for before charging (POST, priced by the server)
    quote_bodies = {
        f"{U}/order/extra/quote": {
            "vendor_id": pid, "address_id": str(w["address"].user_address_id),
            "delivery_date": "2026-10-07", "meal_slot": "lunch", "items": [{"package_id": pkg, "quantity": 1}],
        },
        f"{U}/subscription/quote": {
            "vendor_id": pid, "plan_id": str(w["plan"].subscription_plan_id), "package_id": pkg, "quantity": 1,
            "address_id": str(w["address"].user_address_id), "start_date": "2026-10-07",
        },
    }
    pkg2 = str(f.package(db, w["kitchen"], w["category"], price="220").package_id)
    db.commit()
    quote_bodies[f"{U}/subscription/{sub_id}/switch/preview"] = {"new_package_id": pkg2, "old_package_id": pkg}
    fixtures["ids"]["package2"] = pkg2
    for path, body in quote_bodies.items():
        r = client.post(path, headers=me, json=body)
        if r.status_code != 200:
            raise SystemExit(f"POST {path}: {r.status_code} {r.text[:300]}")
        fixtures[f"POST {path}"] = r.json()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixtures, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"wrote {len(fixtures) - 1} responses to {OUT}")
    db.close()


if __name__ == "__main__":
    main()
