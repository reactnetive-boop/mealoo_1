"""Kitchen -> partner -> customer hand-over, codes, settlement and the ledgers."""

import threading
from datetime import datetime
from decimal import Decimal

from app.core import clock
from app.models.delivery_boy_wallet_model import DeliveryBoyWallet
from app.models.order_model import Order
from app.models.platform_ledger_model import PlatformLedgerEntry
from app.models.provider_wallet_model import ProviderWallet
from tests import factories as f

S = "/api/v1/user/subscription"
K = "/api/v1/provider/orders"
D = "/api/v1/delivery"


def _subscribe(client, w):
    r = client.post(S, headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id),
        "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id),
        "start_date": "2026-10-05",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert r.status_code == 200, r.text
    return r.json()["subscription_id"]


def _today_meal(db, sub_id):
    db.expire_all()
    return (
        db.query(Order)
        .filter(Order.subscription_reference_id == sub_id)
        .order_by(Order.order_date)
        .first()
    )


def _ready(client, db, *, set_pricing=None):
    w = f.world(db, balance="5000")
    sub_id = _subscribe(client, w)
    boy, boy_auth = f.delivery_boy(db, kitchen=w["kitchen"])
    meal = _today_meal(db, sub_id)
    oid = str(meal.order_id)
    assert client.put(f"{K}/subscription-orders/{oid}/status", headers=w["kitchen_auth"], json={"status": "preparing"}).status_code == 200
    r = client.put(f"{K}/subscription-orders/{oid}/assign-delivery-boy", headers=w["kitchen_auth"],
                   json={"delivery_boy_id": str(boy.delivery_boy_id)})
    assert r.status_code == 200, r.text
    return w, sub_id, meal, boy, boy_auth


def test_kitchen_never_sees_customer_delivery_code(client, db):
    w = f.world(db, balance="5000")
    _subscribe(client, w)
    r = client.get(f"{K}/subscription-orders", headers=w["kitchen_auth"], params={"order_date": "2026-10-05"})
    assert r.status_code == 200, r.text
    text = r.text
    for o in r.json()["orders"]:
        assert "otp_for_delivery" not in o
    meal = db.query(Order).first()
    assert meal.otp_for_delivery not in text


def test_kitchen_cannot_mark_delivered_or_loop_statuses(client, db):
    w = f.world(db, balance="5000")
    sub_id = _subscribe(client, w)
    oid = str(_today_meal(db, sub_id).order_id)
    hdr = w["kitchen_auth"]
    assert client.put(f"{K}/subscription-orders/{oid}/status", headers=hdr, json={"status": "delivered"}).status_code in (400, 403, 409)
    assert client.put(f"{K}/subscription-orders/{oid}/status", headers=hdr, json={"status": "preparing"}).status_code == 200
    assert client.put(f"{K}/subscription-orders/{oid}/status", headers=hdr, json={"status": "scheduled"}).status_code in (400, 403, 409)


def test_other_kitchen_cannot_touch_order(client, db):
    w = f.world(db, balance="5000")
    sub_id = _subscribe(client, w)
    oid = str(_today_meal(db, sub_id).order_id)
    _, other_hdr = f.provider(db)
    assert client.put(f"{K}/subscription-orders/{oid}/status", headers=other_hdr, json={"status": "preparing"}).status_code == 404


def test_full_handover_and_single_settlement(client, db):
    w, sub_id, meal, boy, boy_auth = _ready(client, db)
    oid = str(meal.order_id)

    # pickup needs the kitchen's code
    assert client.put(f"{D}/orders/{oid}/pickup", headers=boy_auth, json={"pickup_code": "0000" if meal.pickup_code != "0000" else "1111"}).status_code == 400
    r = client.put(f"{D}/orders/{oid}/pickup", headers=boy_auth, json={"pickup_code": meal.pickup_code})
    assert r.status_code == 200, r.text

    r = client.put(f"{D}/orders/{oid}/deliver", headers=boy_auth, json={"otp": meal.otp_for_delivery})
    assert r.status_code == 200, r.text
    # a retry does not pay twice
    assert client.put(f"{D}/orders/{oid}/deliver", headers=boy_auth, json={"otp": meal.otp_for_delivery}).status_code == 200

    db.expire_all()
    kitchen_wallet = db.query(ProviderWallet).filter(ProviderWallet.provider_reference_id == w["kitchen"].provider_id).one()
    partner_wallet = db.query(DeliveryBoyWallet).filter(DeliveryBoyWallet.delivery_boy_reference_id == boy.delivery_boy_id).one()
    assert kitchen_wallet.balance == Decimal("180.00")
    assert partner_wallet.balance == Decimal("30.00")
    payouts = db.query(PlatformLedgerEntry).filter(PlatformLedgerEntry.entry_type == "delivery_partner_payout").all()
    assert len(payouts) == 1 and payouts[0].amount == Decimal("30.00")


def test_wrong_delivery_codes_lock_the_order(client, db):
    w, sub_id, meal, boy, boy_auth = _ready(client, db)
    oid = str(meal.order_id)
    client.put(f"{D}/orders/{oid}/pickup", headers=boy_auth, json={"pickup_code": meal.pickup_code})
    wrong = "000000" if meal.otp_for_delivery != "000000" else "111111"
    for _ in range(5):
        assert client.put(f"{D}/orders/{oid}/deliver", headers=boy_auth, json={"otp": wrong}).status_code == 400
    r = client.put(f"{D}/orders/{oid}/deliver", headers=boy_auth, json={"otp": meal.otp_for_delivery})
    assert r.status_code == 423
    assert r.json()["code"] == "DELIVERY_LOCKED"


def test_concurrent_deliveries_settle_once(client, db):
    w, sub_id, meal, boy, boy_auth = _ready(client, db)
    oid = str(meal.order_id)
    client.put(f"{D}/orders/{oid}/pickup", headers=boy_auth, json={"pickup_code": meal.pickup_code})
    codes = []

    def go():
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            codes.append(c.put(f"{D}/orders/{oid}/deliver", headers=boy_auth, json={"otp": meal.otp_for_delivery}).status_code)

    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert set(codes) == {200}
    db.expire_all()
    assert db.query(ProviderWallet).one().balance == Decimal("180.00")
    assert db.query(DeliveryBoyWallet).one().balance == Decimal("30.00")


def test_unassigned_or_unapproved_partner_cannot_act(client, db):
    w, sub_id, meal, boy, boy_auth = _ready(client, db)
    other, other_auth = f.delivery_boy(db)
    oid = str(meal.order_id)
    assert client.put(f"{D}/orders/{oid}/pickup", headers=other_auth, json={"pickup_code": meal.pickup_code}).status_code == 404
    pending, pending_auth = f.delivery_boy(db, approved=False)
    assert client.get(f"{D}/orders", headers=pending_auth).status_code == 403
    assert client.get(f"{D}/me/state", headers=pending_auth).json()["next_step"] == "awaiting_approval"


def test_pickup_only_on_delivery_day(client, db):
    w, sub_id, meal, boy, boy_auth = _ready(client, db)
    clock.freeze(datetime(2026, 10, 6, 8, 0))
    r = client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth, json={"pickup_code": meal.pickup_code})
    assert r.status_code == 400


def test_pricing_charges_flow_to_platform_ledger(client, db):
    _, admin_hdr = f.admin(db)
    r = client.put("/api/v1/admin/pricing/delivery_charge", headers=admin_hdr, json={
        "calc_type": "fixed", "value": "10", "charge_basis": "per_delivery", "change_reason": "launch delivery fee",
    })
    assert r.status_code == 200, r.text
    r = client.put("/api/v1/admin/pricing/platform_commission", headers=admin_hdr, json={
        "calc_type": "percentage", "value": "5", "charge_basis": "per_order", "change_reason": "launch commission",
    })
    assert r.status_code == 200, r.text

    w, sub_id, meal, boy, boy_auth = _ready(client, db)
    # 7 lunches x 180 = 1260 food, +70 delivery, +63 commission
    from app.models.subscription_model import Subscription
    sub = db.query(Subscription).filter(Subscription.subscription_id == sub_id).one()
    assert sub.final_amount == Decimal("1393.00")
    assert sub.charges_amount == Decimal("133.00")

    client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth, json={"pickup_code": meal.pickup_code})
    client.put(f"{D}/orders/{meal.order_id}/deliver", headers=boy_auth, json={"otp": meal.otp_for_delivery})
    db.expire_all()
    entries = {
        (e.entry_type, e.direction): e.amount
        for e in db.query(PlatformLedgerEntry).filter(PlatformLedgerEntry.reference_id == meal.order_id)
    }
    assert entries[("delivery_charge", "credit")] == Decimal("10.00")
    assert entries[("commission", "credit")] == Decimal("9.00")
    assert entries[("delivery_partner_payout", "debit")] == Decimal("30.00")
    # kitchen still earns its full base price
    assert db.query(ProviderWallet).one().balance == Decimal("180.00")

    # a later price change does not touch this subscription
    client.put("/api/v1/admin/pricing/delivery_charge", headers=admin_hdr, json={
        "calc_type": "fixed", "value": "50", "charge_basis": "per_delivery", "change_reason": "raise fee",
    })
    db.expire_all()
    assert db.query(Subscription).filter(Subscription.subscription_id == sub_id).one().final_amount == Decimal("1393.00")
