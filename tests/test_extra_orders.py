"""One-time orders: date windows, cut-offs, holidays, capacity, kitchen decisions, refunds, sweeps."""

from datetime import date, datetime
from decimal import Decimal

from app.core import clock
from app.models.extra_order_model import ExtraOrder
from app.models.provider_unavailability_model import ProviderUnavailability
from app.models.wallet_model import Wallet
from app.schedulers import jobs
from tests import factories as f

E = "/api/v1/user/order/extra"
K = "/api/v1/provider/orders"


def _body(w, day="2026-10-05", slot="lunch", qty=1, pkg=None):
    return {
        "vendor_id": str(w["kitchen"].provider_id),
        "address_id": str(w["address"].user_address_id),
        "delivery_date": day,
        "meal_slot": slot,
        "items": [{"package_id": str((pkg or w["package"]).package_id), "quantity": qty}],
    }


def _balance(db, user):
    db.expire_all()
    return db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).one().balance


def test_quote_and_place_use_selling_price(client, db):
    w = f.world(db, price="180", discounted="160", balance="1000")
    q = client.post(f"{E}/quote", headers=w["user_auth"], json=_body(w, qty=2))
    assert q.status_code == 200, q.text
    assert Decimal(q.json()["total_payable"]) == Decimal("320.00")
    r = client.post(E, headers=w["user_auth"], json=_body(w, qty=2))
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["total_amount"]) == Decimal("320.00")
    assert _balance(db, w["user"]) == Decimal("680.00")


def test_date_window_and_cutoffs(client, db):
    w = f.world(db, balance="5000")
    hdr = w["user_auth"]
    assert client.post(E, headers=hdr, json=_body(w, day="2026-10-04")).status_code == 400  # past
    assert client.post(E, headers=hdr, json=_body(w, day="2026-10-20")).status_code == 400  # > 9 days ahead
    clock.freeze(datetime(2026, 10, 5, 9, 5))
    r = client.post(E, headers=hdr, json=_body(w, day="2026-10-05"))
    assert r.status_code == 400 and r.json()["code"] == "CUTOFF_PASSED"
    assert client.post(E, headers=hdr, json=_body(w, day="2026-10-06")).status_code == 200


def test_slot_must_be_served_by_package(client, db):
    w = f.world(db, balance="5000", meal_type="lunch")
    assert client.post(E, headers=w["user_auth"], json=_body(w, slot="dinner")).status_code == 400


def test_holiday_blocks_orders(client, db):
    w = f.world(db, balance="5000")
    db.add(ProviderUnavailability(provider_reference_id=w["kitchen"].provider_id, unavailable_date=date(2026, 10, 6)))
    db.commit()
    r = client.post(E, headers=w["user_auth"], json=_body(w, day="2026-10-06"))
    assert r.status_code == 400 and r.json()["code"] == "KITCHEN_HOLIDAY"


def test_kitchen_daily_limit(client, db):
    w = f.world(db, balance="5000", quota=2)
    assert client.post(E, headers=w["user_auth"], json=_body(w, qty=2)).status_code == 200
    r = client.post(E, headers=w["user_auth"], json=_body(w, qty=1))
    assert r.status_code == 400 and r.json()["code"] == "DAILY_LIMIT_FULL"


def test_customer_cancel_refunds_once(client, db):
    w = f.world(db, balance="1000")
    oid = client.post(E, headers=w["user_auth"], json=_body(w, day="2026-10-06")).json()["orders"][0]["extra_order_id"]
    assert client.put(f"{E}/{oid}/cancel", headers=w["user_auth"]).status_code == 200
    assert client.put(f"{E}/{oid}/cancel", headers=w["user_auth"]).status_code == 400
    assert _balance(db, w["user"]) == Decimal("1000.00")


def test_kitchen_decline_refunds_and_confirmed_cannot_be_customer_cancelled(client, db):
    w = f.world(db, balance="1000")
    a = client.post(E, headers=w["user_auth"], json=_body(w)).json()["orders"][0]["extra_order_id"]
    b = client.post(E, headers=w["user_auth"], json=_body(w)).json()["orders"][0]["extra_order_id"]
    assert client.put(f"{K}/extra/{a}/status", headers=w["kitchen_auth"], json={"status": "cancelled"}).status_code == 200
    assert client.put(f"{K}/extra/{b}/status", headers=w["kitchen_auth"], json={"status": "confirmed"}).status_code == 200
    assert client.put(f"{E}/{b}/cancel", headers=w["user_auth"]).status_code == 400
    assert _balance(db, w["user"]) == Decimal("820.00")


def test_unconfirmed_orders_cancelled_at_cutoff(client, db):
    w = f.world(db, balance="1000")
    oid = client.post(E, headers=w["user_auth"], json=_body(w)).json()["orders"][0]["extra_order_id"]
    jobs.cutoff_sweep_job()  # 05:00, nothing has passed yet
    db.expire_all()
    assert db.query(ExtraOrder).one().status == "pending"
    clock.freeze(datetime(2026, 10, 5, 9, 1))
    jobs.cutoff_sweep_job()
    jobs.cutoff_sweep_job()
    db.expire_all()
    order = db.query(ExtraOrder).one()
    assert order.status == "cancelled" and order.cancel_reason == "kitchen_not_confirmed"
    assert _balance(db, w["user"]) == Decimal("1000.00")
    assert str(order.extra_order_id) == oid


def test_holiday_sweep_cancels_unmoved_meals(client, db):
    w = f.world(db, balance="5000")
    sub = client.post("/api/v1/user/subscription", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-06",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert sub.status_code == 200, sub.text
    before = _balance(db, w["user"])
    r = client.post("/api/v1/provider/holidays", headers=w["kitchen_auth"], json={"date": "2026-10-06", "reason": "family event"})
    assert r.status_code == 200, r.text
    clock.freeze(datetime(2026, 10, 6, 9, 1))
    jobs.cutoff_sweep_job()
    assert _balance(db, w["user"]) == before + Decimal("180.00")


def test_stale_sweep_refunds_past_unfulfilled(client, db):
    w = f.world(db, balance="1000")
    client.post(E, headers=w["user_auth"], json=_body(w))
    oid = db.query(ExtraOrder).one().extra_order_id
    client.put(f"{K}/extra/{oid}/status", headers=w["kitchen_auth"], json={"status": "confirmed"})
    clock.freeze(datetime(2026, 10, 6, 0, 30))
    jobs.stale_sweep_job()
    db.expire_all()
    assert db.query(ExtraOrder).one().status == "cancelled"
    assert _balance(db, w["user"]) == Decimal("1000.00")


def test_other_customer_cannot_see_order(client, db):
    w = f.world(db, balance="1000")
    oid = client.post(E, headers=w["user_auth"], json=_body(w)).json()["orders"][0]["extra_order_id"]
    _, _, stranger = f.customer(db)
    assert client.get(f"{E}/{oid}", headers=stranger).status_code == 404
    assert client.put(f"{E}/{oid}/cancel", headers=stranger).status_code == 404
