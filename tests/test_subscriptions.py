"""Subscriptions: pricing, creation, today's meal, generation, skip, pause/resume, cancel, expiry."""

import threading
from datetime import date, datetime
from decimal import Decimal

from app.core import clock
from app.models.order_model import Order
from app.models.subscription_model import Subscription
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction
from app.schedulers import jobs
from tests import factories as f

S = "/api/v1/user/subscription"


def _body(w, start="2026-10-05", qty=1, **extra):
    return {
        "vendor_id": str(w["kitchen"].provider_id),
        "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id),
        "start_date": start,
        "items": [{"package_id": str(w["package"].package_id), "quantity": qty}],
        **extra,
    }


def _balance(db, user):
    db.expire_all()
    return db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).one().balance


def _meals(db, sub_id):
    db.expire_all()
    return db.query(Order).filter(Order.subscription_reference_id == sub_id).order_by(Order.order_date).all()


def test_quote_matches_charge_and_today_meal_is_created(client, db):
    w = f.world(db, price="180", balance="5000")
    q = client.post(f"{S}/quote", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "package_id": str(w["package"].package_id),
        "plan_id": str(w["plan"].subscription_plan_id), "address_id": str(w["address"].user_address_id),
        "start_date": "2026-10-05",
    })
    assert q.status_code == 200, q.text
    assert Decimal(q.json()["total_payable"]) == Decimal("1260.00")

    r = client.post(S, headers=w["user_auth"], json=_body(w))
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["final_amount"]) == Decimal("1260.00")
    assert _balance(db, w["user"]) == Decimal("3740.00")

    meals = _meals(db, r.json()["subscription_id"])
    assert len(meals) == 7
    assert meals[0].order_date == date(2026, 10, 5)  # today's lunch exists (before 09:00 cut-off)
    assert all(m.otp_for_delivery and len(m.otp_for_delivery) == 6 for m in meals)
    assert all(m.pickup_code and len(m.pickup_code) == 4 for m in meals)


def test_selling_price_is_discounted_price_not_discount_amount(client, db):
    # 180 MRP, 160 selling: the subscription unit price falls back to the selling price
    w = f.world(db, price="180", discounted="160", sub_price="150", balance="5000")
    r = client.post(S, headers=w["user_auth"], json=_body(w))
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["final_amount"]) == Decimal("1050.00")  # 150 x 7, never 20 x 7


def test_start_today_after_cutoff_rejected(client, db):
    w = f.world(db)
    clock.freeze(datetime(2026, 10, 5, 10, 0))  # after the 09:00 lunch cut-off
    r = client.post(S, headers=w["user_auth"], json=_body(w, start="2026-10-05"))
    assert r.status_code == 400
    assert r.json().get("code") == "START_DATE_TOO_EARLY"
    assert client.post(S, headers=w["user_auth"], json=_body(w, start="2026-10-06")).status_code == 200


def test_insufficient_balance_creates_nothing(client, db):
    w = f.world(db, balance="100")
    r = client.post(S, headers=w["user_auth"], json=_body(w))
    assert r.status_code == 400
    assert r.json()["code"] == "INSUFFICIENT_BALANCE"
    assert db.query(Subscription).count() == 0
    assert db.query(Order).count() == 0


def test_idempotency_key_replay_charges_once(client, db):
    w = f.world(db, balance="5000")
    hdr = {**w["user_auth"], "Idempotency-Key": "checkout-1"}
    a = client.post(S, headers=hdr, json=_body(w))
    b = client.post(S, headers=hdr, json=_body(w))
    assert a.status_code == b.status_code == 200
    assert a.json()["subscription_id"] == b.json()["subscription_id"]
    assert db.query(Subscription).count() == 1
    assert _balance(db, w["user"]) == Decimal("3740.00")


def test_concurrent_checkouts_never_overspend(client, db):
    # money for exactly one subscription; two parallel checkouts
    w = f.world(db, balance="1300")
    results = []

    def go(key):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            results.append(c.post(S, headers={**w["user_auth"], "Idempotency-Key": key}, json=_body(w)).status_code)

    threads = [threading.Thread(target=go, args=(f"k{i}",)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [200, 400]
    assert db.query(Subscription).count() == 1
    assert _balance(db, w["user"]) == Decimal("40.00")


def test_meal_generation_is_idempotent(client, db):
    w = f.world(db, balance="5000")
    sub_id = client.post(S, headers=w["user_auth"], json=_body(w)).json()["subscription_id"]
    jobs.generate_meals_job()
    jobs.generate_meals_job()
    assert len(_meals(db, sub_id)) == 7


def test_free_skip_refunds_once_and_late_skip_does_not(client, db):
    w = f.world(db, balance="5000", skips=1)
    sub_id = client.post(S, headers=w["user_auth"], json=_body(w)).json()["subscription_id"]
    meals = _meals(db, sub_id)
    before = _balance(db, w["user"])

    r = client.put(f"{S}/{sub_id}/orders/{meals[1].order_id}/skip", headers=w["user_auth"])
    assert r.status_code == 200, r.text
    assert r.json()["is_free_skip"] is True
    assert Decimal(r.json()["refund_amount"]) == Decimal("180.00")
    # skipping the same meal again does not refund again
    assert client.put(f"{S}/{sub_id}/orders/{meals[1].order_id}/skip", headers=w["user_auth"]).status_code == 400
    # no free skips left -> skip allowed but not refunded
    r = client.put(f"{S}/{sub_id}/orders/{meals[2].order_id}/skip", headers=w["user_auth"])
    assert r.json()["is_free_skip"] is False
    assert _balance(db, w["user"]) == before + Decimal("180.00")
    # the retired billing job must not refund skips a second time
    from app.schedulers.order_billing import process_order_billing
    process_order_billing("lunch")
    assert _balance(db, w["user"]) == before + Decimal("180.00")


def test_skip_after_cutoff_is_not_refunded(client, db):
    w = f.world(db, balance="5000", skips=3)
    sub_id = client.post(S, headers=w["user_auth"], json=_body(w)).json()["subscription_id"]
    today_meal = _meals(db, sub_id)[0]
    before = _balance(db, w["user"])
    clock.freeze(datetime(2026, 10, 5, 9, 30))
    r = client.put(f"{S}/{sub_id}/orders/{today_meal.order_id}/skip", headers=w["user_auth"])
    assert r.status_code == 200
    assert r.json()["not_free_reason"] == "cutoff_passed"
    assert _balance(db, w["user"]) == before


def test_pause_and_resume_extend_end_date(client, db):
    w = f.world(db, balance="5000")
    sub_id = client.post(S, headers=w["user_auth"], json=_body(w)).json()["subscription_id"]
    assert client.put(f"{S}/{sub_id}/pause", headers=w["user_auth"]).status_code == 200
    statuses = [m.status for m in _meals(db, sub_id)]
    assert statuses[0] == "scheduled" and set(statuses[1:]) == {"cancelled"}

    clock.freeze(datetime(2026, 10, 7, 5, 0))  # two days later
    r = client.put(f"{S}/{sub_id}/resume", headers=w["user_auth"])
    assert r.status_code == 200, r.text
    db.expire_all()
    sub = db.query(Subscription).filter(Subscription.subscription_id == sub_id).one()
    assert sub.status == "active"
    assert sub.end_date == date(2026, 10, 14)  # 12 Oct + 2 paused days
    jobs.generate_meals_job()
    delivered_or_due = [m for m in _meals(db, sub_id) if m.status == "scheduled"]
    assert len(delivered_or_due) == 7  # still exactly the 7 meals paid for


def test_cancel_refunds_unstarted_meals_once(client, db):
    w = f.world(db, balance="5000")
    sub_id = client.post(S, headers=w["user_auth"], json=_body(w)).json()["subscription_id"]
    clock.freeze(datetime(2026, 10, 5, 10, 0))  # today's lunch already being cooked
    r = client.put(f"{S}/{sub_id}/cancel", headers=w["user_auth"], json={"cancel_reason": "moving"})
    assert r.status_code == 200, r.text
    assert r.json()["cancelled_meals"] == 6
    assert Decimal(r.json()["refund_amount"]) == Decimal("1080.00")
    assert _balance(db, w["user"]) == Decimal("3740.00") + Decimal("1080.00")
    assert client.put(f"{S}/{sub_id}/cancel", headers=w["user_auth"], json={}).status_code == 400
    assert _balance(db, w["user"]) == Decimal("4820.00")


def test_expiry_job(client, db):
    w = f.world(db, balance="5000")
    sub_id = client.post(S, headers=w["user_auth"], json=_body(w)).json()["subscription_id"]
    clock.freeze(datetime(2026, 10, 12, 1, 0))
    jobs.expire_subscriptions_job()
    db.expire_all()
    assert db.query(Subscription).filter(Subscription.subscription_id == sub_id).one().status == "expired"


def test_custom_plan_needs_end_date(client, db):
    w = f.world(db, balance="5000")
    custom = f.plan(db, sub_type="custom", slot="lunch", days=0)
    body = _body(w)
    body["plan_id"] = str(custom.subscription_plan_id)
    assert client.post(S, headers=w["user_auth"], json=body).status_code == 400
    body["end_date"] = "2026-10-09"  # last meal date, inclusive
    r = client.post(S, headers=w["user_auth"], json=body)
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["final_amount"]) == Decimal("900.00")  # 5 lunches


def test_two_slot_plan_needs_package_serving_both(client, db):
    w = f.world(db, balance="9000", meal_type="lunch")
    both = f.plan(db, sub_type="weekly", slot="lunch_dinner", days=7)
    body = _body(w)
    body["plan_id"] = str(both.subscription_plan_id)
    assert client.post(S, headers=w["user_auth"], json=body).status_code == 400
    pkg = f.package(db, w["kitchen"], w["category"], meal_type="lunch,dinner")
    body["items"][0]["package_id"] = str(pkg.package_id)
    r = client.post(S, headers=w["user_auth"], json=body)
    assert r.status_code == 200, r.text
    assert len(_meals(db, r.json()["subscription_id"])) == 14


def test_kitchen_controls_block_sales(client, db):
    w = f.world(db, balance="5000")
    w["kitchen"].is_accepting_orders = False
    db.commit()
    assert client.post(S, headers=w["user_auth"], json=_body(w)).status_code in (400, 409)
    w["kitchen"].is_accepting_orders = True
    w["package"].approval_status = "pending"
    db.commit()
    assert client.post(S, headers=w["user_auth"], json=_body(w)).status_code in (400, 404, 409)


def test_capacity_is_enforced_per_date(client, db):
    w = f.world(db, balance="9000", capacity=1)
    other, _, other_auth = f.customer(db, balance="5000")
    assert client.post(S, headers=w["user_auth"], json=_body(w)).status_code == 200
    body = _body(w)
    from app.models.user_address_model import UserAddress
    body["address_id"] = str(db.query(UserAddress).filter(UserAddress.user_reference_id == other.user_id).one().user_address_id)
    r = client.post(S, headers=other_auth, json=body)
    assert r.status_code == 400
    assert r.json()["code"] in ("CAPACITY_FULL", "DAILY_LIMIT_FULL")
    # after the first plan ends, the same dates are free again
    body["start_date"] = "2026-10-12"
    assert client.post(S, headers=other_auth, json=body).status_code == 200


def test_customer_cannot_touch_another_customers_subscription(client, db):
    w = f.world(db, balance="5000")
    sub_id = client.post(S, headers=w["user_auth"], json=_body(w)).json()["subscription_id"]
    _, _, stranger = f.customer(db)
    assert client.get(f"{S}/{sub_id}", headers=stranger).status_code == 404
    assert client.put(f"{S}/{sub_id}/cancel", headers=stranger, json={}).status_code == 404
    meal = _meals(db, sub_id)[1]
    assert client.put(f"{S}/{sub_id}/orders/{meal.order_id}/skip", headers=stranger).status_code == 404


def test_delivery_code_only_visible_on_meal_day(client, db):
    w = f.world(db, balance="5000")
    sub_id = client.post(S, headers=w["user_auth"], json=_body(w)).json()["subscription_id"]
    rows = client.get(f"{S}/{sub_id}/orders", headers=w["user_auth"]).json()["orders"]
    today = [o for o in rows if o["order_date"] == "2026-10-05"][0]
    later = [o for o in rows if o["order_date"] != "2026-10-05"]
    assert today["otp_for_delivery"]
    assert all(o["otp_for_delivery"] is None for o in later)


def test_wallet_ledger_is_consistent(client, db):
    w = f.world(db, balance="5000")
    client.post(S, headers=w["user_auth"], json=_body(w))
    db.expire_all()
    txns = db.query(WalletTransaction).filter(WalletTransaction.user_reference_id == w["user"].user_id).all()
    net = sum((t.amount if t.type == "credit" else -t.amount) for t in txns)
    assert net == _balance(db, w["user"])
