"""Business-rule gaps closed after the code review (BE-B4, B7, B12, B13)."""

from decimal import Decimal

from app.domain import orders as meals
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.subscription_model import Subscription
from app.models.wallet_model import Wallet
from tests import factories as f

S = "/api/v1/user/subscription"
ADDRESS = {"house_no": "12", "address": "MG Road, Central", "city": "Bengaluru", "state": "Karnataka"}


def _subscribe(client, w, pkg=None):
    r = client.post(S, headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": str((pkg or w["package"]).package_id), "quantity": 1}],
    })
    assert r.status_code == 200, r.text
    return r.json()["subscription_id"]


# ── BE-B4: kitchen cannot move away from customers it already serves ──

def test_kitchen_cannot_change_pincode_while_serving(client, db):
    w = f.world(db)
    f.pincode(db, 560002)
    _subscribe(client, w)
    r = client.put("/api/v1/provider/address", headers=w["kitchen_auth"], json={**ADDRESS, "pincode": 560002})
    assert r.status_code == 409
    assert r.json()["code"] == "KITCHEN_HAS_OPEN_ORDERS"
    # same pincode, new street: fine
    r = client.put("/api/v1/provider/address", headers=w["kitchen_auth"], json={**ADDRESS, "pincode": f.PIN})
    assert r.status_code == 200, r.text


def test_idle_kitchen_can_move(client, db):
    w = f.world(db)
    f.pincode(db, 560002)
    r = client.put("/api/v1/provider/address", headers=w["kitchen_auth"], json={**ADDRESS, "pincode": 560002})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(Provider).filter(Provider.provider_id == w["kitchen"].provider_id).one().pincode == 560002


# ── BE-B7: a switch inside the same kitchen does not count the old plan twice ──

def test_same_kitchen_switch_is_not_blocked_by_its_own_meals(client, db):
    w = f.world(db, quota=1)
    sub_id = _subscribe(client, w)
    other = f.package(db, w["kitchen"], w["category"], price="190")
    r = client.post(f"{S}/{sub_id}/switch", headers=w["user_auth"], json={"new_package_id": str(other.package_id)})
    assert r.status_code == 200, r.text


def test_switch_still_respects_other_customers(client, db):
    w = f.world(db, quota=1)
    _subscribe(client, w)
    _, second_address, second_auth = f.customer(db, balance="5000")
    r = client.post(S, headers=second_auth, json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(second_address.user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert r.status_code == 400 and r.json()["code"] == "DAILY_LIMIT_FULL"


# ── BE-B12: no meals for a kitchen that stopped serving ──

def test_no_meals_generated_for_inactive_kitchen(client, db):
    w = f.world(db)
    sub_id = _subscribe(client, w)
    db.query(Order).filter(Order.subscription_reference_id == sub_id).delete()
    db.query(Provider).filter(Provider.provider_id == w["kitchen"].provider_id).update({"is_active": False})
    db.commit()
    sub = db.query(Subscription).filter(Subscription.subscription_id == sub_id).one()
    assert meals.generate_meals(db, sub) == 0

    # a kitchen that only paused NEW orders keeps serving what it sold
    db.query(Provider).filter(Provider.provider_id == w["kitchen"].provider_id).update(
        {"is_active": True, "is_accepting_orders": False})
    db.commit()
    assert meals.generate_meals(db, sub) > 0


# ── BE-B13: quotes and wallet views never lock or create wallets ──

def test_wallet_view_and_quotes_do_not_create_wallets(client, db):
    w = f.world(db, balance="0")
    assert db.query(Wallet).filter(Wallet.user_reference_id == w["user"].user_id).count() == 0

    r = client.get("/api/v1/user/wallet", headers=w["user_auth"])
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["wallet"]["balance"])) == Decimal("0")

    q = client.post(f"{S}/quote", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-05",
        "package_id": str(w["package"].package_id),
    })
    assert q.status_code == 200, q.text
    assert q.json()["wallet_balance"] in ("0.00", 0, "0")
    db.expire_all()
    assert db.query(Wallet).filter(Wallet.user_reference_id == w["user"].user_id).count() == 0


def test_balance_read_matches_ledger(db):
    from app.domain import ledger

    user, _, _ = f.customer(db, balance="250")
    assert ledger.customer_balance(db, user.user_id) == Decimal("250.00")
    stranger, _, _ = f.customer(db)
    assert ledger.customer_balance(db, stranger.user_id) == Decimal("0.00")
