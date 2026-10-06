"""BE-P6: admin dashboard numbers, trends and cache."""

from decimal import Decimal

from tests import factories as f

S = "/api/v1/user/subscription"
DASH = "/api/v1/admin/dashboard"


def test_dashboard_numbers_trends_and_cache(client, db):
    w = f.world(db, price="100", balance="5000")
    r = client.post(S, headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert r.status_code == 200, r.text
    # rows get the database clock; align the customer with the frozen business clock
    from app.core.clock import now_utc
    from app.models.user_model import User
    db.query(User).update({"created_at": now_utc()})
    db.commit()
    _, hdr = f.admin(db)

    first = client.get(DASH, headers=hdr, params={"refresh": True}).json()
    assert first["cached"] is False
    assert first["users"]["total"] == 1 and first["subscriptions"]["active"] == 1
    assert first["orders"]["today_total"] == 1 and first["orders"]["today_unassigned"] == 1
    days = first["trends"]["days"]
    assert len(days) == 14 and days[-1]["date"] == "2026-10-05"
    assert Decimal(days[-1]["gmv"]) == Decimal("700.00")      # 7 meals x 100 paid today
    assert days[-1]["new_customers"] == 1

    again = client.get(DASH, headers=hdr).json()
    assert again["cached"] is True and again["trends"] == first["trends"]
