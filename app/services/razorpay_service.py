"""
Wallet top-up through Razorpay (PR-01). Off unless PAYMENT_GATEWAY=razorpay.

  1. POST /user/wallet/topup/order  -> a Razorpay order is created and a
     pending Payment row remembers it; the app opens Razorpay Checkout with
     the returned order id and key id.
  2. POST /user/wallet/topup/verify -> the app sends back the ids and the
     signature Checkout returned; HMAC-SHA256(order_id|payment_id, key
     secret) must match. The payment is then credited to the wallet.
  3. POST /payments/razorpay/webhook -> Razorpay's server-to-server event
     (signature over the raw body with the webhook secret). payment.captured
     credits the wallet even if the app never called verify; payment.failed
     marks the payment failed.

Steps 2 and 3 can both arrive, in any order and more than once: the credit is
posted with the payment's idempotency key, so the wallet is credited once.
"""

import hashlib
import hmac
import json
import logging
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from app.core.audit import business_event, security_event
from app.core.clock import now_local, now_utc
from app.core.config import (
    PAYMENT_GATEWAY,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    RAZORPAY_WEBHOOK_SECRET,
    WALLET_TOPUP_DAILY_LIMIT,
    WALLET_TOPUP_MAX_AMOUNT,
)
from app.core.errors import DomainError
from app.domain import notify
from app.domain.pricing import money
from app.models.payment_model import Payment
from app.services.wallet_service import credit_payment

logger = logging.getLogger("app.razorpay")
API = "https://api.razorpay.com/v1"
_transport = None  # tests inject an httpx.MockTransport


def _enabled() -> None:
    if PAYMENT_GATEWAY != "razorpay":
        raise DomainError("Online payment is not available yet", 503, code="GATEWAY_DISABLED")


def _signature_ok(message: bytes, secret: str | None, signature: str | None) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _complete(db: Session, payment: Payment, gateway_payment_id: str, source: str) -> Payment:
    """Mark paid and credit once (verify and webhook may both arrive)."""
    if payment.status == "completed":
        return payment
    payment.status = "completed"
    payment.gateway_txn_id = gateway_payment_id
    payment.paid_at = now_utc()
    credit_payment(db, payment, "Wallet top-up (Razorpay)")
    notify.customer(
        db, payment.user_reference_id, "wallet", "Money added",
        f"Rs {payment.amount} was added to your wallet.", {"payment_id": str(payment.payment_id)},
    )
    business_event("wallet.topup", user_id=payment.user_reference_id, amount=payment.amount,
                   payment_id=payment.payment_id, gateway="razorpay", source=source)
    return payment


class RazorpayService:

    @staticmethod
    def create_order(db: Session, user_id: str, amount) -> dict:
        _enabled()
        amount = money(amount)
        if amount > money(WALLET_TOPUP_MAX_AMOUNT):
            raise DomainError(f"A single top-up can be at most Rs {money(WALLET_TOPUP_MAX_AMOUNT)}")
        from sqlalchemy import func

        day_start = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
        today_total = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
            Payment.user_reference_id == user_id, Payment.purpose == "wallet_topup",
            Payment.status == "completed", Payment.paid_at >= day_start,
        ).scalar()
        if money(today_total) + amount > money(WALLET_TOPUP_DAILY_LIMIT):
            raise DomainError(f"Daily top-up limit of Rs {money(WALLET_TOPUP_DAILY_LIMIT)} reached")

        payment = Payment(
            user_reference_id=user_id, purpose="wallet_topup", amount=amount, currency="INR",
            method="razorpay", status="pending", gateway="razorpay",
        )
        db.add(payment)
        db.flush()
        try:
            with httpx.Client(timeout=10, transport=_transport) as client:
                r = client.post(
                    f"{API}/orders",
                    auth=(RAZORPAY_KEY_ID or "", RAZORPAY_KEY_SECRET or ""),
                    json={"amount": int(amount * 100), "currency": "INR", "receipt": str(payment.payment_id),
                          "notes": {"user_id": str(user_id), "purpose": "wallet_topup"}},
                )
        except httpx.HTTPError:
            raise DomainError("Payment could not be started. Please try again.", 502, code="GATEWAY_ERROR") from None
        if r.status_code >= 400:
            logger.error("razorpay order failed: %s", r.status_code)
            raise DomainError("Payment could not be started. Please try again.", 502, code="GATEWAY_ERROR")
        order = r.json()
        payment.gateway_order_id = order["id"]
        db.commit()
        return {
            "success": True,
            "payment_id": payment.payment_id,
            "razorpay_order_id": order["id"],
            "razorpay_key_id": RAZORPAY_KEY_ID,
            "amount_paise": order["amount"],
            "currency": "INR",
        }

    @staticmethod
    def verify(db: Session, user_id: str, payload) -> dict:
        _enabled()
        message = f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}".encode()
        if not _signature_ok(message, RAZORPAY_KEY_SECRET, payload.razorpay_signature):
            security_event("payment.bad_signature", user_id=user_id)
            raise DomainError("Payment could not be verified", 400, code="BAD_SIGNATURE")
        payment = db.query(Payment).filter(
            Payment.gateway_order_id == payload.razorpay_order_id, Payment.user_reference_id == user_id,
        ).with_for_update().first()
        if payment is None:
            raise DomainError("Payment not found", 404)
        _complete(db, payment, payload.razorpay_payment_id, "verify")
        db.commit()
        return {"success": True, "message": "Money added to your wallet", "payment_id": payment.payment_id,
                "amount": payment.amount}

    @staticmethod
    def webhook(db: Session, raw_body: bytes, signature: str | None) -> dict:
        if PAYMENT_GATEWAY != "razorpay":
            raise DomainError("Not found", 404)
        if not _signature_ok(raw_body, RAZORPAY_WEBHOOK_SECRET, signature):
            security_event("payment.webhook_bad_signature")
            raise DomainError("Invalid signature", 400)
        event = json.loads(raw_body)
        entity = ((event.get("payload") or {}).get("payment") or {}).get("entity") or {}
        order_id = entity.get("order_id")
        payment = (
            db.query(Payment).filter(Payment.gateway_order_id == order_id).with_for_update().first()
            if order_id else None
        )
        if payment is None:
            return {"success": True, "ignored": True}  # not ours; 2xx so Razorpay stops retrying
        kind = event.get("event")
        if kind == "payment.captured":
            if Decimal(entity.get("amount", 0)) != payment.amount * 100:
                security_event("payment.amount_mismatch", payment_id=payment.payment_id)
                raise DomainError("Amount mismatch", 400)
            _complete(db, payment, entity.get("id"), "webhook")
        elif kind == "payment.failed" and payment.status == "pending":
            payment.status = "failed"
            payment.failure_reason = (entity.get("error_description") or "")[:255] or "failed"
        db.commit()
        return {"success": True}
