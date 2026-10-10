"""Customers can't cancel their own plans or one-time orders (admins still can)."""

from decimal import Decimal

from tests import factories as f
from tests.test_extra_orders import E, _body as extra_body
from tests.test_subscriptions import S, _balance, _body as sub_body

A = "/api/v1/admin"


def test_customer_cannot_cancel_a_plan(client, db):
    w = f.world(db, balance="5000")
    sub_id = client.post(S, headers=w["user_auth"], json=sub_body(w)).json()["subscription_id"]
    before = _balance(db, w["user"])

    r = client.put(f"{S}/{sub_id}/cancel", headers=w["user_auth"], json={"cancel_reason": "changed mind"})
    assert r.status_code == 403
    assert r.json()["code"] == "CANCELLATION_DISABLED"
    assert _balance(db, w["user"]) == before

    detail = client.get(f"{S}/{sub_id}", headers=w["user_auth"]).json()
    assert (detail.get("subscription") or detail)["can_cancel"] is False


def test_customer_cannot_cancel_a_one_time_order(client, db):
    w = f.world(db, balance="1000")
    oid = client.post(E, headers=w["user_auth"], json=extra_body(w, day="2026-10-06")).json()["orders"][0]["extra_order_id"]
    before = _balance(db, w["user"])

    r = client.put(f"{E}/{oid}/cancel", headers=w["user_auth"])
    assert r.status_code == 403
    assert r.json()["code"] == "CANCELLATION_DISABLED"
    assert _balance(db, w["user"]) == before
    assert client.get(f"{E}/{oid}", headers=w["user_auth"]).json()["can_cancel"] is False


def test_another_customers_order_is_still_not_found(client, db):
    w = f.world(db, balance="1000")
    oid = client.post(E, headers=w["user_auth"], json=extra_body(w, day="2026-10-06")).json()["orders"][0]["extra_order_id"]
    _, _, stranger = f.customer(db)
    assert client.put(f"{E}/{oid}/cancel", headers=stranger).status_code == 404


def test_admin_can_still_cancel_a_plan(client, db):
    _, hdr = f.admin(db)
    w = f.world(db, balance="5000")
    sub_id = client.post(S, headers=w["user_auth"], json=sub_body(w)).json()["subscription_id"]
    r = client.put(f"{A}/users/subscriptions/{sub_id}/cancel", headers=hdr, params={"reason": "customer asked support"})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["refund_amount"]) > 0
