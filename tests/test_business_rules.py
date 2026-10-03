"""Catalogue packages, package switch, reviews, addresses, wallet top-up limits, kitchen onboarding rules."""

from datetime import datetime
from decimal import Decimal

from app.core import clock
from app.models.order_model import Order
from app.models.subscription_model import Subscription
from app.models.wallet_model import Wallet
from tests import factories as f

S = "/api/v1/user/subscription"


def _subscribe(client, w, pkg=None, vendor=None, start="2026-10-05"):
    return client.post(S, headers=w["user_auth"], json={
        "vendor_id": str((vendor or w["kitchen"]).provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": start,
        "items": [{"package_id": str((pkg or w["package"]).package_id), "quantity": 1}],
    })


def _balance(db, user):
    db.expire_all()
    return db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).one().balance


def test_catalogue_package_sold_by_offering_kitchen(client, db):
    w = f.world(db, balance="5000")
    cat_pkg = f.package(db, None, w["category"], price="150", predefined=True)
    # not offered yet by this kitchen
    assert _subscribe(client, w, pkg=cat_pkg).status_code in (400, 404)
    r = client.post("/api/v1/provider-package/select", headers=w["kitchen_auth"], json={"package_id": str(cat_pkg.package_id), "daily_capacity": 10})
    assert r.status_code == 200, r.text
    r = _subscribe(client, w, pkg=cat_pkg)
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["final_amount"]) == Decimal("1050.00")


def test_kitchen_cannot_edit_catalogue_package(client, db):
    w = f.world(db)
    cat_pkg = f.package(db, None, w["category"], predefined=True)
    f.offer(db, w["kitchen"], cat_pkg)
    r = client.put(f"/api/v1/menu/update/{cat_pkg.package_id}", headers=w["kitchen_auth"], json={"price": "1"})
    assert r.status_code == 404


def test_switch_charges_only_the_difference(client, db):
    w = f.world(db, price="180", balance="5000")
    sub_id = _subscribe(client, w).json()["subscription_id"]
    dearer = f.package(db, w["kitchen"], w["category"], price="200")
    before = _balance(db, w["user"])
    prev = client.post(f"{S}/{sub_id}/switch/preview", headers=w["user_auth"], json={"new_package_id": str(dearer.package_id)})
    assert prev.status_code == 200, prev.text
    r = client.post(f"{S}/{sub_id}/switch", headers=w["user_auth"], json={"new_package_id": str(dearer.package_id)})
    assert r.status_code == 200, r.text
    db.expire_all()
    old = db.query(Subscription).filter(Subscription.subscription_id == sub_id).one()
    assert old.status in ("switched", "active")
    # 6 remaining meals from tomorrow: 6 x (200 - 180) = 120
    assert before - _balance(db, w["user"]) == Decimal("120.00")
    # no meal is served twice on the same date and slot
    rows = db.query(Order).filter(Order.user_reference_id == w["user"].user_id, Order.status == "scheduled").all()
    keys = [(o.order_date, o.meal_slot) for o in rows]
    assert len(keys) == len(set(keys))


def test_review_requires_a_delivered_purchase(client, db):
    w = f.world(db, balance="5000")
    sub_id = _subscribe(client, w).json()["subscription_id"]
    body = {"vendor_id": str(w["kitchen"].provider_id), "vendor_rating": 5, "subscription_id": sub_id}
    assert client.post("/api/v1/user/review", headers=w["user_auth"], json=body).status_code in (400, 403)
    _, _, stranger = f.customer(db)
    assert client.post("/api/v1/user/review", headers=stranger, json=body).status_code in (400, 403, 404)


def test_address_in_use_cannot_change_pincode_or_be_deleted(client, db):
    w = f.world(db, balance="5000")
    _subscribe(client, w)
    aid = w["address"].user_address_id
    r = client.put(f"/api/v1/user/address/{aid}", headers=w["user_auth"], json={"pin_code": "560002"})
    assert r.status_code in (400, 409)
    assert client.delete(f"/api/v1/user/address/{aid}", headers=w["user_auth"]).status_code in (400, 409)
    _, _, stranger = f.customer(db)
    assert client.get(f"/api/v1/user/address/{aid}", headers=stranger).status_code == 404


def test_wallet_topup_limits_and_idempotency(client, db):
    user, _, hdr = f.customer(db)
    assert client.post("/api/v1/user/wallet/recharge", headers=hdr, json={"amount": "10001"}).status_code == 400
    assert client.post("/api/v1/user/wallet/recharge", headers=hdr, json={"amount": "-5"}).status_code == 422
    for i in range(2):
        assert client.post("/api/v1/user/wallet/recharge", headers={**hdr, "Idempotency-Key": f"t{i}"}, json={"amount": "10000"}).status_code == 200
    r = client.post("/api/v1/user/wallet/recharge", headers={**hdr, "Idempotency-Key": "t3"}, json={"amount": "6000"})
    assert r.status_code == 400  # 25,000 per day
    assert _balance(db, user) == Decimal("20000.00")


def test_kitchen_profile_needs_serviceable_pincode(client, db):
    f.pincode(db, 560001)
    kitchen, hdr = f.provider(db, approved=False, complete=False)
    body = {
        "full_name": "Asha Cook", "business_name": "Asha Kitchen", "city": "Pune", "area": "Central",
        "address": "12 FC Road", "kitchen_type": "home", "pincode": 411001, "house_no": "1", "state": "MH",
        "meal_service_type": "Lunch", "daily_meal_quota": 30,
    }
    r = client.put("/api/v1/provider/complete-profile", headers=hdr, json=body)
    assert r.status_code == 400 and r.json().get("code") == "PINCODE_NOT_SERVICEABLE"
    body["pincode"] = 560001
    assert client.put("/api/v1/provider/complete-profile", headers=hdr, json=body).status_code == 200


def test_business_dates_use_india_time(client, db):
    # 23:30 UTC on 4 Oct is already 5 Oct 05:00 in India
    clock.freeze(datetime.fromisoformat("2026-10-04T23:30:00+00:00"))
    assert client.get("/api/v1/public/config").json()["business_date"] == "2026-10-05"


def test_withdrawal_limits(client, db):
    kitchen, hdr = f.provider(db)
    assert client.post("/api/v1/provider/wallet/withdraw", headers=hdr, json={"amount": "10"}).status_code == 400  # no balance
    assert client.post("/api/v1/provider/wallet/withdraw", headers=hdr, json={"amount": "0"}).status_code == 422
