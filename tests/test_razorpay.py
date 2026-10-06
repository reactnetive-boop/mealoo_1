"""PR-01: Razorpay wallet top-up (verify + webhook credit exactly once)."""

import hashlib
import hmac
import json
from decimal import Decimal

import httpx
import pytest

from app.models.payment_model import Payment
from app.models.wallet_model import Wallet
from app.services import razorpay_service as rz
from tests import factories as f

W = "/api/v1/user/wallet"
KEY_SECRET = "rzp_test_secret"
HOOK_SECRET = "rzp_hook_secret"


@pytest.fixture
def gateway(monkeypatch):
    def handler(request: httpx.Request):
        body = json.loads(request.content)
        return httpx.Response(200, json={"id": "order_ABC123", "amount": body["amount"], "currency": "INR"})

    monkeypatch.setattr(rz, "PAYMENT_GATEWAY", "razorpay")
    monkeypatch.setattr(rz, "RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setattr(rz, "RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setattr(rz, "RAZORPAY_WEBHOOK_SECRET", HOOK_SECRET)
    monkeypatch.setattr(rz, "_transport", httpx.MockTransport(handler))


def _sign(secret, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _balance(db, user):
    db.expire_all()
    row = db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).first()
    return row.balance if row else Decimal("0")


def test_disabled_by_default(client, db):
    _, _, hdr = f.customer(db)
    r = client.post(f"{W}/topup/order", headers=hdr, json={"amount": "100"})
    assert r.status_code == 503 and r.json()["code"] == "GATEWAY_DISABLED"


def test_checkout_verify_and_webhook_credit_once(client, db, gateway):
    user, _, hdr = f.customer(db)
    order = client.post(f"{W}/topup/order", headers=hdr, json={"amount": "250"}).json()
    assert order["razorpay_order_id"] == "order_ABC123" and order["amount_paise"] == 25000

    bad = {"razorpay_order_id": "order_ABC123", "razorpay_payment_id": "pay_1", "razorpay_signature": "0" * 64}
    assert client.post(f"{W}/topup/verify", headers=hdr, json=bad).status_code == 400
    good = {**bad, "razorpay_signature": _sign(KEY_SECRET, b"order_ABC123|pay_1")}
    assert client.post(f"{W}/topup/verify", headers=hdr, json=good).status_code == 200
    assert _balance(db, user) == Decimal("250.00")

    event = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_1", "order_id": "order_ABC123", "amount": 25000}}}}).encode()
    r = client.post("/api/v1/payments/razorpay/webhook", content=event,
                    headers={"X-Razorpay-Signature": _sign(HOOK_SECRET, event), "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    assert _balance(db, user) == Decimal("250.00")  # verify + webhook = one credit
    assert db.query(Payment).one().status == "completed"


def test_webhook_alone_credits_and_rejects_forgeries(client, db, gateway):
    user, _, hdr = f.customer(db)
    client.post(f"{W}/topup/order", headers=hdr, json={"amount": "100"})
    event = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_2", "order_id": "order_ABC123", "amount": 10000}}}}).encode()
    forged = client.post("/api/v1/payments/razorpay/webhook", content=event, headers={"X-Razorpay-Signature": "x"})
    assert forged.status_code == 400 and _balance(db, user) == Decimal("0")
    ok = client.post("/api/v1/payments/razorpay/webhook", content=event,
                     headers={"X-Razorpay-Signature": _sign(HOOK_SECRET, event)})
    assert ok.status_code == 200 and _balance(db, user) == Decimal("100.00")
