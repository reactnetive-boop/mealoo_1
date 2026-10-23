"""
Hand-over verification codes.

pickup    One 6-digit code per kitchen per business day. The kitchen reads it
          to the delivery partner when handing over food; the partner enters
          it to record the pickup. A code only ever works for its own kitchen
          and its own day, and it only comes into being once the kitchen has
          an order to hand over that day (never at sign-up, never on an empty
          day).
delivery  One 6-digit code per order. The customer reads it to the partner at
          the door; the partner enters it to complete the delivery. A code
          only ever works for its own order.

Codes are never stored. Each row keeps a random seed and the code is
HMAC(server key, purpose | subject | seed) reduced to six digits, so a copy
of the database reveals no codes, the kitchen / customer can still be shown
theirs, and a new seed gives a new code. The subject (kitchen + date, or the
order id) is part of the input, so one code can never match another kitchen,
day or order. Comparisons are constant-time; attempt limits live with the
callers (per order and per partner per day).
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import date, time, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.audit import record_audit, business_event
from app.core.clock import now_utc, now_local, local_datetime
from app.core.config import DELIVERY_CODE_GRACE_HOURS, JWT_SECRET_KEY, VERIFICATION_CODE_SECRET
from app.core.errors import DomainError
from app.domain.status import SUB_UNPICKED_STATUSES, EXTRA_UNPICKED_STATUSES
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from app.models.provider_pickup_code_model import ProviderPickupCode

CODE_LENGTH = 6

NO_PICKUP_CODE_MESSAGE = "No orders for today yet. Your pickup code appears here once an order comes in."


def new_seed() -> str:
    return secrets.token_hex(16)


def _key() -> bytes:
    # Separate from the JWT and OTP keys even when derived from the same secret
    secret = VERIFICATION_CODE_SECRET or f"verification::{JWT_SECRET_KEY}"
    return hashlib.sha256(secret.encode()).digest()


def derive(purpose: str, subject: str, seed: str) -> str:
    digest = hmac.new(_key(), f"{purpose}|{subject}|{seed}".encode(), hashlib.sha256).digest()
    # 64 bits mod 10^6: the bias is far below one in a billion
    return f"{int.from_bytes(digest[:8], 'big') % 10 ** CODE_LENGTH:0{CODE_LENGTH}d}"


def matches(entered: str | None, expected: str | None) -> bool:
    if not entered or not expected:
        return False
    return hmac.compare_digest(entered.encode(), expected.encode())


def end_of_day(on: date):
    """First instant of the next business day (codes for `on` expire here)."""
    return local_datetime(on + timedelta(days=1), time(0))


# ── Customer delivery code (per order) ────────────────────────

def order_ref(order) -> str:
    return str(getattr(order, "order_id", None) or getattr(order, "extra_order_id"))


def order_day(order) -> date:
    return getattr(order, "order_date", None) or getattr(order, "delivery_date")


def code_subject(order) -> str:
    """One code per delivery: lines of a one-time checkout share theirs (seed prefix "c:")."""
    seed = order.delivery_code_seed or ""
    checkout_id = getattr(order, "checkout_id", None)
    if checkout_id and seed.startswith("c:"):
        return f"checkout:{checkout_id}"
    return order_ref(order)


def delivery_code(order) -> str | None:
    if order.delivery_code_seed:
        return derive("delivery", code_subject(order), order.delivery_code_seed)
    # rows written before seeds existed
    return order.otp_for_delivery


def delivery_code_expired(order) -> bool:
    expires = end_of_day(order_day(order)) + timedelta(hours=DELIVERY_CODE_GRACE_HOURS)
    return now_utc() >= expires


# ── Kitchen pickup code (per kitchen per day) ─────────────────

def _subject(provider_id, on: date) -> str:
    return f"{provider_id}:{on.isoformat()}"


def pickup_code_value(row: ProviderPickupCode) -> str:
    return derive("pickup", _subject(row.provider_reference_id, row.code_date), row.code_seed)


def has_orders_to_hand_over(db: Session, provider_id, on: date) -> bool:
    """The kitchen has at least one order for `on` that is still waiting to be picked up."""
    return db.query(
        db.query(Order.order_id).filter(
            Order.vendor_reference_id == provider_id,
            Order.order_date == on,
            Order.status.in_(SUB_UNPICKED_STATUSES),
        ).exists()
    ).scalar() or db.query(
        db.query(ExtraOrder.extra_order_id).filter(
            ExtraOrder.vendor_reference_id == provider_id,
            ExtraOrder.delivery_date == on,
            ExtraOrder.status.in_(EXTRA_UNPICKED_STATUSES),
        ).exists()
    ).scalar()


def find_pickup_code_row(db: Session, provider_id, on: date, *, lock: bool = False) -> ProviderPickupCode | None:
    """The kitchen's existing code row for `on`; never creates one."""
    q = db.query(ProviderPickupCode).filter(
        ProviderPickupCode.provider_reference_id == provider_id,
        ProviderPickupCode.code_date == on,
    )
    if lock:
        q = q.with_for_update()
    return q.one_or_none()


def pickup_code_row(db: Session, provider_id, on: date, *, lock: bool = False) -> ProviderPickupCode | None:
    """
    The kitchen's code row for `on`, created on first use - but only once the
    kitchen has an order to hand over that day. A kitchen with no orders gets
    no row (None), so nothing is generated at sign-up or on an empty day.

    Creation is INSERT ... ON CONFLICT DO NOTHING on (kitchen, day), so
    concurrent first uses (kitchen opening the app, a partner verifying, the
    daily job) all end up with the same single row and never a duplicate.
    """

    row = find_pickup_code_row(db, provider_id, on, lock=lock)
    if row is not None:
        return row
    if not has_orders_to_hand_over(db, provider_id, on):
        return None

    inserted = db.execute(
        pg_insert(ProviderPickupCode)
        .values(
            pickup_code_id=uuid.uuid4(),
            provider_reference_id=provider_id,
            code_date=on,
            code_seed=new_seed(),
            version=1,
            status="active",
            expires_at=end_of_day(on),
            created_by_type="system",
        )
        .on_conflict_do_nothing(index_elements=["provider_reference_id", "code_date"])
    ).rowcount
    if inserted:
        record_audit(
            db, table="provider.provider_pickup_codes", operation="I",
            new={"event": "pickup_code_generated", "provider_id": provider_id, "code_date": on},
            actor_type="system",
        )
        business_event("pickup_code.generated", provider_id=provider_id, code_date=on)

    return find_pickup_code_row(db, provider_id, on, lock=lock)


def pickup_code_usable(row: ProviderPickupCode | None, on: date) -> bool:
    return row is not None and row.status == "active" and row.code_date == on and now_local() < row.expires_at


def regenerate_pickup_code(db: Session, provider_id, on: date, *, actor_id, actor_type: str, ip: str | None = None) -> ProviderPickupCode:
    row = pickup_code_row(db, provider_id, on, lock=True)
    if row is None:
        raise DomainError(NO_PICKUP_CODE_MESSAGE, 404, code="NO_PICKUP_CODE")
    row.code_seed = new_seed()
    row.version = (row.version or 1) + 1
    row.status = "active"
    row.regenerated_at = now_utc()
    row.created_by_type = actor_type
    record_audit(
        db, table="provider.provider_pickup_codes", record_id=row.pickup_code_id,
        new={"event": "pickup_code_regenerated", "provider_id": provider_id, "code_date": on, "version": row.version},
        actor_id=actor_id, actor_type=actor_type, ip=ip,
    )
    db.flush()
    return row
