"""Admin controls: approvals, data exposure, money actions, roles, audit."""

from decimal import Decimal

from app.models.audit_log_model import AuditLog
from app.models.delivery_boy_document_model import DeliveryBoyDocument
from app.models.order_model import Order
from app.models.platform_ledger_model import PlatformLedgerEntry
from app.models.provider_wallet_model import ProviderWallet
from app.models.wallet_model import Wallet
from tests import factories as f

A = "/api/v1/admin"


def _sub(client, w):
    r = client.post("/api/v1/user/subscription", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert r.status_code == 200, r.text
    return r.json()["subscription_id"]


def test_admin_responses_never_leak_secrets(client, db):
    _, hdr = f.admin(db)
    w = f.world(db, balance="5000")
    _sub(client, w)
    f.delivery_boy(db)
    for path in ("/providers", f"/providers/{w['kitchen'].provider_id}", "/users", f"/users/{w['user'].user_id}",
                 "/delivery-boys", "/orders/subscription-orders", "/orders/subscriptions"):
        r = client.get(A + path, headers=hdr)
        assert r.status_code == 200, (path, r.text)
        body = r.text
        for secret in ("hashed_password", "password_hash", "otp_for_delivery", "pickup_code", "token_version", "$2b$"):
            assert secret not in body, (path, secret)


def test_kitchen_approval_gates_selling(client, db):
    _, hdr = f.admin(db, role="moderator")
    f.pincode(db)
    cat = f.category(db)
    kitchen, kitchen_hdr = f.provider(db, approved=False)
    pkg = f.package(db, kitchen, cat)
    _, _, user_hdr = f.customer(db)
    listed = client.get("/api/v1/user/menu/packages", headers=user_hdr, params={"pin_code": "560001"}).json()
    assert str(pkg.package_id) not in str(listed)

    assert client.put(f"{A}/providers/{kitchen.provider_id}/reject", headers=hdr, json={}).status_code == 400
    r = client.put(f"{A}/providers/{kitchen.provider_id}/approve", headers=hdr)
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/provider/me/state", headers=kitchen_hdr).json()["next_step"] == "dashboard"
    listed = client.get("/api/v1/user/menu/packages", headers=user_hdr, params={"pin_code": "560001"}).json()
    assert str(pkg.package_id) in str(listed)
    assert db.query(AuditLog).filter(AuditLog.table_name == "provider.providers").count() >= 1


def test_package_approval_flow(client, db):
    _, hdr = f.admin(db, role="moderator")
    f.pincode(db)
    cat = f.category(db)
    kitchen, _ = f.provider(db)
    pkg = f.package(db, kitchen, cat, approved=False)
    _, _, user_hdr = f.customer(db)
    assert str(pkg.package_id) not in client.get("/api/v1/user/menu/packages", headers=user_hdr, params={"pin_code": "560001"}).text
    r = client.put(f"{A}/packages/{pkg.package_id}/reject", headers=hdr, json={"note": "Photos missing"})
    assert r.status_code == 200
    r = client.put(f"{A}/packages/{pkg.package_id}/approve", headers=hdr)
    assert r.status_code == 200, r.text
    assert str(pkg.package_id) in client.get("/api/v1/user/menu/packages", headers=user_hdr, params={"pin_code": "560001"}).text


def test_delivery_partner_approval_requires_verified_documents(client, db):
    _, hdr = f.admin(db)
    boy, boy_hdr = f.delivery_boy(db, approved=False)
    r = client.put(f"{A}/delivery-boys/{boy.delivery_boy_id}/approve", headers=hdr)
    assert r.status_code == 400
    docs = db.query(DeliveryBoyDocument).filter(DeliveryBoyDocument.delivery_boy_reference_id == boy.delivery_boy_id).all()
    for d in docs:
        r = client.put(f"{A}/delivery-boys/{boy.delivery_boy_id}/documents/{d.delivery_boy_document_id}/review",
                       headers=hdr, json={"status": "verified"})
        assert r.status_code == 200, r.text
    assert client.put(f"{A}/delivery-boys/{boy.delivery_boy_id}/approve", headers=hdr).status_code == 200
    assert client.get("/api/v1/delivery/me/state", headers=boy_hdr).json()["next_step"] == "dashboard"


def test_moderator_cannot_move_money_or_change_pricing(client, db):
    _, mod = f.admin(db, role="moderator")
    user, _, _ = f.customer(db, balance="100")
    kitchen, _ = f.provider(db)
    body = {"amount": "50", "type": "credit", "reason": "goodwill"}
    assert client.post(f"{A}/users/{user.user_id}/wallet/adjust", headers=mod, json=body).status_code == 403
    assert client.post(f"{A}/providers/{kitchen.provider_id}/wallet/adjust", headers=mod, json=body).status_code == 403
    assert client.put(f"{A}/users/{user.user_id}/status", headers=mod, json={"status": "suspended"}).status_code == 403
    assert client.put(f"{A}/pricing/delivery_charge", headers=mod, json={
        "calc_type": "fixed", "value": "5", "charge_basis": "per_delivery", "change_reason": "test change",
    }).status_code == 403


def test_wallet_adjust_is_idempotent_ledgered_and_audited(client, db):
    _, hdr = f.admin(db)
    user, _, _ = f.customer(db, balance="100")
    h = {**hdr, "Idempotency-Key": "adj-1"}
    body = {"amount": "50", "type": "credit", "reason": "late delivery compensation"}
    assert client.post(f"{A}/users/{user.user_id}/wallet/adjust", headers=h, json=body).status_code == 200
    assert client.post(f"{A}/users/{user.user_id}/wallet/adjust", headers=h, json=body).status_code == 200
    db.expire_all()
    assert db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).one().balance == Decimal("150.00")
    assert db.query(PlatformLedgerEntry).filter(PlatformLedgerEntry.entry_type == "manual_adjustment").count() == 1
    r = client.post(f"{A}/users/{user.user_id}/wallet/adjust", headers=hdr,
                    json={"amount": "500", "type": "debit", "reason": "too much"})
    assert r.status_code == 400  # never below zero


def test_force_status_settles_or_refunds_once(client, db):
    _, hdr = f.admin(db)
    w = f.world(db, balance="5000")
    sub_id = _sub(client, w)
    meals = db.query(Order).filter(Order.subscription_reference_id == sub_id).order_by(Order.order_date).all()
    r = client.put(f"{A}/orders/subscription-orders/{meals[0].order_id}/status", headers=hdr,
                   json={"status": "delivered", "reason": "confirmed by phone with customer"})
    assert r.status_code == 200, r.text
    assert client.put(f"{A}/orders/subscription-orders/{meals[0].order_id}/status", headers=hdr,
                      json={"status": "cancelled", "reason": "flip back attempt"}).status_code in (400, 409)
    db.expire_all()
    assert db.query(ProviderWallet).one().balance == Decimal("180.00")

    r = client.put(f"{A}/orders/subscription-orders/{meals[1].order_id}/status", headers=hdr,
                   json={"status": "cancelled", "reason": "kitchen issue"})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["refund_amount"]) == Decimal("180.00")
    # reason is mandatory
    assert client.put(f"{A}/orders/subscription-orders/{meals[2].order_id}/status", headers=hdr,
                      json={"status": "cancelled"}).status_code == 422


def test_admin_cancel_subscription_refunds(client, db):
    _, hdr = f.admin(db)
    w = f.world(db, balance="5000")
    sub_id = _sub(client, w)
    r = client.put(f"{A}/users/subscriptions/{sub_id}/cancel", headers=hdr, params={"reason": "fraud check"})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["refund_amount"]) == Decimal("1260.00")


def test_blocking_user_revokes_sessions(client, db):
    _, hdr = f.admin(db)
    user, _, user_hdr = f.customer(db)
    assert client.put(f"{A}/users/{user.user_id}/status", headers=hdr, json={"status": "suspended", "reason": "abuse"}).status_code == 200
    assert client.get("/api/v1/user/me/state", headers=user_hdr).status_code in (401, 403)


def test_pincode_in_use_cannot_be_deleted(client, db):
    _, hdr = f.admin(db)
    pin = f.pincode(db)
    f.provider(db)
    assert client.delete(f"{A}/pincodes/{pin.pincode_id}", headers=hdr).status_code == 400
    r = client.put(f"{A}/pincodes/{pin.pincode_id}", headers=hdr, json={"is_active": False})
    assert r.status_code == 200


def test_plan_validation(client, db):
    _, hdr = f.admin(db)
    ok = client.post(f"{A}/plans", headers=hdr, json={"subscription_type": "monthly", "meal_slot": "lunch_dinner", "duration_days": 30})
    assert ok.status_code == 200, ok.text
    assert client.post(f"{A}/plans", headers=hdr, json={"subscription_type": "monthly", "meal_slot": "brunch", "duration_days": 30}).status_code == 400
    custom = client.post(f"{A}/plans", headers=hdr, json={"subscription_type": "custom", "meal_slot": "all"})
    assert custom.status_code == 200 and custom.json()["plan"]["meal_slot"] == "all_slots"


def test_pricing_versions_and_history(client, db):
    _, hdr = f.admin(db)
    for v in ("5", "7"):
        assert client.put(f"{A}/pricing/sms_charge", headers=hdr, json={
            "calc_type": "fixed", "value": v, "charge_basis": "per_order", "change_reason": f"set to {v}",
        }).status_code == 200
    current = {c["component_key"]: c for c in client.get(f"{A}/pricing", headers=hdr).json()["components"]}
    assert current["sms_charge"]["version"] == 3 and Decimal(current["sms_charge"]["value"]) == Decimal("7")
    history = client.get(f"{A}/pricing/history", headers=hdr, params={"component_key": "sms_charge"}).json()
    assert history["total"] == 3
    assert client.put(f"{A}/pricing/sms_charge", headers=hdr, json={
        "calc_type": "percentage", "value": "150", "charge_basis": "per_order", "change_reason": "bad value",
    }).status_code == 422
    prev = client.post(f"{A}/pricing/preview", headers=hdr, json={"base_unit_price": "100", "deliveries": 7}).json()["quote"]
    assert Decimal(prev["total_payable"]) == Decimal("707.00")


def test_withdrawal_hold_paid_and_rejected(client, db):
    _, hdr = f.admin(db)
    kitchen, kitchen_hdr = f.provider(db)
    from app.domain import ledger
    ledger.post_provider(db, kitchen.provider_id, type="credit", amount=Decimal("500"), reason="order_delivered",
                         idempotency_key="seed-earning", counts_as_earning=True)
    db.commit()
    r = client.post("/api/v1/provider/wallet/withdraw", headers=kitchen_hdr, json={"amount": "300"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(ProviderWallet).one().balance == Decimal("200.00")  # held
    req_id = client.get(f"{A}/payouts", headers=hdr, params={"status": "pending"}).json()["requests"][0]["payout_request_id"]
    assert client.put(f"{A}/payouts/{req_id}", headers=hdr, json={"action": "paid"}).status_code == 400  # reference needed
    r = client.put(f"{A}/payouts/{req_id}", headers=hdr, json={"action": "paid", "payout_reference": "UTR123456"})
    assert r.status_code == 200, r.text
    assert client.put(f"{A}/payouts/{req_id}", headers=hdr, json={"action": "rejected"}).status_code == 409

    r = client.post("/api/v1/provider/wallet/withdraw", headers=kitchen_hdr, json={"amount": "200"})
    req2 = client.get(f"{A}/payouts", headers=hdr, params={"status": "pending"}).json()["requests"][0]["payout_request_id"]
    assert client.put(f"{A}/payouts/{req2}", headers=hdr, json={"action": "rejected", "admin_note": "bank mismatch"}).status_code == 200
    db.expire_all()
    w = db.query(ProviderWallet).one()
    assert w.balance == Decimal("200.00") and w.total_withdrawn == Decimal("300.00")


def test_holiday_reassignment_moves_meal(client, db):
    _, hdr = f.admin(db)
    w = f.world(db, balance="5000")
    sub_id = _sub(client, w)
    other, _ = f.provider(db)
    meal = db.query(Order).filter(Order.subscription_reference_id == sub_id).order_by(Order.order_date).all()[1]
    body = {"new_provider_id": str(other.provider_id), "reason": "holiday cover"}
    # current kitchen must be on holiday first
    assert client.put(f"{A}/orders/subscription-orders/{meal.order_id}/reassign-provider", headers=hdr, json=body).status_code == 400
    assert client.post(f"{A}/providers/{w['kitchen'].provider_id}/unavailability", headers=hdr,
                       json={"date": str(meal.order_date), "reason": "closed"}).status_code == 200
    r = client.put(f"{A}/orders/subscription-orders/{meal.order_id}/reassign-provider", headers=hdr, json=body)
    assert r.status_code == 200, r.text
