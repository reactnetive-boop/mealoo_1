"""
Delivery partner hand-over actions.

pickup:   only the assigned partner, on the order's date, once the kitchen
          is preparing it (or marked it ready), with the kitchen's pickup
          code for that day. Wrong codes are counted per order (locks after
          PICKUP_CODE_MAX_ATTEMPTS) and per partner per day
          (PICKUP_CODE_DAILY_FAILURE_LIMIT), and every attempt is audited.
start:    picked_up -> out_for_delivery ("Start delivery"); the customer is
          told the meal is on the way.
arrived:  the partner reached the door; the customer is told once.
deliver:  only the assigned partner, only after pickup, with the customer's
          code for that order. Wrong codes are counted; after
          DELIVERY_CODE_MAX_ATTEMPTS the order locks and needs admin help.

Every state change runs on a row-locked order, so concurrent or replayed
requests cannot pick up / deliver (and pay) twice; a replay of an action that
already happened returns success without changing anything. The codes
themselves are never returned to the partner.
"""

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import record_audit, security_event, business_event
from app.core.clock import now_utc, today_local
from app.core.config import (
    DELIVERY_CODE_MAX_ATTEMPTS,
    DELIVERY_FAILED_WAIT_MINUTES,
    PICKUP_CODE_DAILY_FAILURE_LIMIT,
    PICKUP_CODE_MAX_ATTEMPTS,
)
from app.core.errors import DomainError
from app.domain import checkout, notify, orders as meals
from app.domain.status import (
    assert_sub_order_transition,
    assert_extra_order_transition,
    IN_HAND_STATUSES,
    PICKUP_READY_STATUSES,
)
from app.domain.verification import (
    delivery_code,
    delivery_code_expired,
    matches,
    order_day,
    order_ref,
    pickup_code_row,
    pickup_code_usable,
    pickup_code_value,
)
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order


from app.services.delivery_views import _pickup_locked

_NOT_STARTED = ("scheduled", "pending", "confirmed")

FAILURE_REASONS = {
    "customer_unavailable": "customer not reachable",
    "wrong_address": "address could not be found",
    "customer_refused": "customer refused the order",
    "other": "partner reported a problem",
}


# ── Locking and auditing helpers ──────────────────────────────

def _locked(db: Session, kind: str, order_id, delivery_boy_id):
    if kind == "subscription":
        q = db.query(Order).filter(Order.order_id == order_id, Order.delivery_boy_reference_id == delivery_boy_id)
    else:
        q = db.query(ExtraOrder).filter(
            ExtraOrder.extra_order_id == order_id, ExtraOrder.delivery_boy_reference_id == delivery_boy_id
        )
    # Another partner's order is indistinguishable from a missing one
    order = q.with_for_update().first()
    if order is None:
        raise DomainError("Order not found", 404)
    return order


def _assert(kind: str, current: str, target: str) -> None:
    if kind == "subscription":
        assert_sub_order_transition(current, target, "delivery_boy")
    else:
        assert_extra_order_transition(current, target, "delivery_boy")


def _audit_verification(db: Session, order, kind: str, step: str, result: str, delivery_boy_id, ip, reason: str | None = None) -> None:
    # The code itself is never written anywhere
    record_audit(
        db,
        table="subscription.orders" if kind == "subscription" else "subscription.extra_orders",
        record_id=order_ref(order),
        new={
            "event": f"{step}_verification",
            "result": result,
            "reason": reason,
            "order_kind": kind,
            "subscription_id": getattr(order, "subscription_reference_id", None),
            "provider_id": order.vendor_reference_id,
            "customer_id": order.user_reference_id,
            "delivery_boy_id": delivery_boy_id,
            "pickup_attempts": order.pickup_code_attempts or 0,
            "delivery_attempts": order.delivery_code_attempts or 0,
        },
        actor_id=delivery_boy_id,
        actor_type="delivery_boy",
        ip=ip,
    )


def _daily_pickup_failures(db: Session, delivery_boy_id, on: date) -> int:
    subs = db.query(func.coalesce(func.sum(Order.pickup_code_attempts), 0)).filter(
        Order.delivery_boy_reference_id == delivery_boy_id, Order.order_date == on
    ).scalar()
    extras = db.query(func.coalesce(func.sum(ExtraOrder.pickup_code_attempts), 0)).filter(
        ExtraOrder.delivery_boy_reference_id == delivery_boy_id, ExtraOrder.delivery_date == on
    ).scalar()
    return int(subs or 0) + int(extras or 0)


def _result(order, message: str, already: bool = False, others: list | None = None) -> dict:
    others = others or []
    if others:
        message += f" ({len(others) + 1} packages of the same order)"
    return {
        "success": True,
        "message": message,
        "order_id": order_ref(order),
        "status": order.status,
        "already_done": already,
        # other lines of the same one-time checkout that moved with this one
        "also_updated": [order_ref(o) for o in others],
    }


def _travelling_with(db: Session, order, kind: str, delivery_boy_id, statuses) -> list:
    """Other lines of a one-time checkout in this partner's care: one trip, so they move together."""
    if kind == "subscription":
        return []
    return checkout.siblings(db, order, statuses=statuses, delivery_boy_id=delivery_boy_id)


class DeliveryHandoverService:

    # ── Hand-over actions (both order kinds) ──────────────

    @staticmethod
    def pickup(db: Session, delivery_boy_id: str, kind: str, order_id, payload, ip: str | None = None):
        order = _locked(db, kind, order_id, delivery_boy_id)
        if order.status in IN_HAND_STATUSES or order.status == "delivered":
            return _result(order, "Order already picked up", already=True)

        day = order_day(order)
        today = today_local()
        if day != today:
            raise DomainError("Orders can only be picked up on their delivery date", code="NOT_PICKUP_DAY")
        if order.status in _NOT_STARTED:
            raise DomainError("The kitchen has not started preparing this order yet", code="NOT_READY_FOR_PICKUP")
        if order.status not in PICKUP_READY_STATUSES:
            _assert(kind, order.status, "picked_up")  # cancelled / skipped: explains why

        attempts = order.pickup_code_attempts or 0
        if attempts >= PICKUP_CODE_MAX_ATTEMPTS:
            raise DomainError(
                "Too many wrong pickup codes. This order is locked - please contact Orleeno support.",
                423,
                code="PICKUP_LOCKED",
            )
        if _daily_pickup_failures(db, delivery_boy_id, today) >= PICKUP_CODE_DAILY_FAILURE_LIMIT:
            raise DomainError(
                "Too many wrong pickup codes today. Please contact Orleeno support.",
                429,
                code="PICKUP_VERIFICATION_BLOCKED",
            )

        # Only this order's kitchen's code for today can match
        code_row = pickup_code_row(db, order.vendor_reference_id, day)
        usable = pickup_code_usable(code_row, day)
        if not usable or not matches(payload.pickup_code, pickup_code_value(code_row)):
            order.pickup_code_attempts = attempts + 1
            _audit_verification(
                db, order, kind, "pickup", "failed", delivery_boy_id, ip,
                reason="code_expired" if not usable else "wrong_code",
            )
            db.commit()
            security_event(
                "delivery.pickup_code_failed", order=order_ref(order), kind=kind,
                delivery_boy_id=delivery_boy_id, attempts=order.pickup_code_attempts,
            )
            left = PICKUP_CODE_MAX_ATTEMPTS - order.pickup_code_attempts
            raise DomainError(
                f"Invalid pickup code. Please ask the kitchen for today's pickup code. {left} attempt(s) left.",
                code="INVALID_PICKUP_CODE",
            )

        _assert(kind, order.status, "picked_up")
        others = _travelling_with(db, order, kind, delivery_boy_id, PICKUP_READY_STATUSES)
        for line in [order, *others]:
            _assert(kind, line.status, "picked_up")
            line.status = "picked_up"
            line.picked_up_at = now_utc()
        if getattr(payload, "delivery_notes", None) and kind == "subscription":
            order.delivery_notes = payload.delivery_notes
        _audit_verification(db, order, kind, "pickup", "success", delivery_boy_id, ip)
        db.commit()
        business_event("order.picked_up", order_id=order_ref(order), kind=kind, delivery_boy_id=delivery_boy_id,
                       lines=1 + len(others))
        return _result(order, "Pickup verified. Order picked up.", others=others)

    @staticmethod
    def start_delivery(db: Session, delivery_boy_id: str, kind: str, order_id):
        order = _locked(db, kind, order_id, delivery_boy_id)
        if order.status in ("out_for_delivery", "delivered"):
            return _result(order, "Delivery already started", already=True)
        if order.status not in IN_HAND_STATUSES:
            raise DomainError("Verify the pickup at the kitchen first", code="NOT_PICKED_UP")
        _assert(kind, order.status, "out_for_delivery")
        others = _travelling_with(db, order, kind, delivery_boy_id, ("picked_up",))
        for line in [order, *others]:
            line.status = "out_for_delivery"
            line.out_for_delivery_at = now_utc()
        notify.customer(
            db, order.user_reference_id, "order_status", "Out for delivery",
            f"Your {order.meal_slot} is on the way. Keep your delivery code ready - it is on your Home screen.",
            {"order_id": order_ref(order), "kind": kind},
        )
        db.commit()
        return _result(order, "Delivery started", others=others)

    @staticmethod
    def mark_arrived(db: Session, delivery_boy_id: str, kind: str, order_id):
        order = _locked(db, kind, order_id, delivery_boy_id)
        if order.status == "delivered":
            return _result(order, "Order already delivered", already=True)
        if order.status not in IN_HAND_STATUSES:
            raise DomainError("Verify the pickup at the kitchen first", code="NOT_PICKED_UP")
        others = _travelling_with(db, order, kind, delivery_boy_id, IN_HAND_STATUSES)
        for line in [order, *others]:
            if line.status == "picked_up":
                line.status = "out_for_delivery"
                line.out_for_delivery_at = line.out_for_delivery_at or now_utc()
        already = order.arrived_at is not None
        for line in others:
            line.arrived_at = line.arrived_at or now_utc()
        if not already:
            order.arrived_at = now_utc()
            notify.customer(
                db, order.user_reference_id, "order_status", "Your delivery partner is here",
                f"Your {order.meal_slot} has arrived. Share your delivery code with the delivery partner.",
                {"order_id": order_ref(order), "kind": kind},
            )
        db.commit()
        return _result(order, "Customer notified", already=already, others=others)

    @staticmethod
    def deliver(db: Session, delivery_boy_id: str, kind: str, order_id, payload, ip: str | None = None):
        order = _locked(db, kind, order_id, delivery_boy_id)
        if order.status == "delivered":
            # A retried request after success: nothing more to do
            return _result(order, "Order already delivered", already=True)
        if order.status not in IN_HAND_STATUSES:
            if order.status in PICKUP_READY_STATUSES or order.status in _NOT_STARTED:
                raise DomainError("Verify the pickup at the kitchen first", code="NOT_PICKED_UP")
            _assert(kind, order.status, "delivered")

        attempts = order.delivery_code_attempts or 0
        if attempts >= DELIVERY_CODE_MAX_ATTEMPTS:
            raise DomainError(
                "Too many wrong codes. This delivery is locked - please contact Orleeno support.",
                423,
                code="DELIVERY_LOCKED",
            )
        if delivery_code_expired(order):
            _audit_verification(db, order, kind, "delivery", "failed", delivery_boy_id, ip, reason="code_expired")
            db.commit()
            raise DomainError(
                "This delivery code has expired. Please contact Orleeno support.",
                code="DELIVERY_CODE_EXPIRED",
            )
        if not matches(payload.otp, delivery_code(order)):
            order.delivery_code_attempts = attempts + 1
            _audit_verification(db, order, kind, "delivery", "failed", delivery_boy_id, ip, reason="wrong_code")
            db.commit()
            security_event(
                "delivery.code_failed", order=order_ref(order), kind=kind,
                delivery_boy_id=delivery_boy_id, attempts=order.delivery_code_attempts,
            )
            left = DELIVERY_CODE_MAX_ATTEMPTS - order.delivery_code_attempts
            raise DomainError(
                f"Invalid delivery code. Please ask the customer to provide the correct code. {left} attempt(s) left.",
                code="INVALID_DELIVERY_CODE",
            )

        _assert(kind, order.status, "delivered")
        others = _travelling_with(db, order, kind, delivery_boy_id, IN_HAND_STATUSES)
        for line in [order, *others]:
            if line.status == "picked_up":
                line.out_for_delivery_at = line.out_for_delivery_at or now_utc()
            line.status = "delivered"
            line.delivered_at = now_utc()
        if getattr(payload, "delivery_notes", None) and kind == "subscription":
            order.delivery_notes = payload.delivery_notes
        if kind == "subscription":
            meals.settle_subscription_meal(db, order)
        else:
            # every line pays its kitchen; the partner is paid once for the trip
            for line in [order, *others]:
                meals.settle_extra_order(db, line)
        notify.customer(
            db, order.user_reference_id, "order_status", "Delivered",
            f"Your {order.meal_slot} for {order_day(order)} was delivered. Enjoy your meal!",
            {"order_id": order_ref(order), "kind": kind},
        )
        _audit_verification(db, order, kind, "delivery", "success", delivery_boy_id, ip)
        db.commit()
        business_event("order.delivered", order_id=order_ref(order), kind=kind, delivery_boy_id=delivery_boy_id,
                       lines=1 + len(others))
        return _result(order, "Delivery verified. Order delivered.", others=others)

    @staticmethod
    def fail_delivery(db: Session, delivery_boy_id: str, kind: str, order_id, payload, ip: str | None = None):
        """
        The partner reached the customer but could not hand over. Allowed only
        after "arrived" was pressed (the customer was notified) and the partner
        waited DELIVERY_FAILED_WAIT_MINUTES. The food was cooked and the trip
        made, so the kitchen and the partner are paid and the customer is not
        refunded; an admin can still reverse it (refund or mark delivered).
        """
        order = _locked(db, kind, order_id, delivery_boy_id)
        if order.status == "delivery_failed":
            return _result(order, "Already reported", already=True)
        if order.status not in IN_HAND_STATUSES:
            raise DomainError("Only an order you are carrying can be reported as not delivered", code="NOT_PICKED_UP")
        if order.arrived_at is None:
            raise DomainError("Tap 'Arrived' first so the customer is told you are at the door", code="NOT_ARRIVED")
        waited = (now_utc() - order.arrived_at).total_seconds() / 60
        if waited < DELIVERY_FAILED_WAIT_MINUTES:
            left = int(DELIVERY_FAILED_WAIT_MINUTES - waited) + 1
            raise DomainError(f"Please wait {left} more minute(s) for the customer before reporting",
                              code="WAIT_FOR_CUSTOMER")

        _assert(kind, order.status, "delivery_failed")
        others = _travelling_with(db, order, kind, delivery_boy_id, IN_HAND_STATUSES)
        for line in [order, *others]:
            line.status = "delivery_failed"
            line.failed_at = now_utc()
            line.failure_reason = payload.reason
        if kind == "subscription":
            meals.settle_subscription_meal(db, order)
        else:
            for line in [order, *others]:
                meals.settle_extra_order(db, line)
        notify.customer(
            db, order.user_reference_id, "order_status", "We could not deliver your meal",
            f"Your {order.meal_slot} for {order_day(order)} could not be handed over "
            f"({FAILURE_REASONS[payload.reason]}). If this is wrong, raise a complaint from the order.",
            {"order_id": order_ref(order), "kind": kind},
        )
        record_audit(
            db, table="subscription.orders" if kind == "subscription" else "subscription.extra_orders",
            record_id=order_ref(order),
            new={"event": "delivery_failed", "reason": payload.reason, "note": payload.note,
                 "waited_minutes": round(waited, 1)},
            actor_id=delivery_boy_id, actor_type="delivery_boy", ip=ip,
        )
        db.commit()
        business_event("order.delivery_failed", order_id=order_ref(order), kind=kind, reason=payload.reason)
        return _result(order, "Reported as not delivered", others=others)

    # ── Bulk pickup (one code for everything ready at a kitchen) ──

    @staticmethod
    def pickup_all(db: Session, delivery_boy_id: str, provider_id, pickup_code: str, ip: str | None = None):
        """
        Collect every order of this partner that is ready at this kitchen today
        with one entry of the kitchen's pickup code. Same limits as a single
        pickup: a wrong code counts once toward the daily limit, and orders
        locked by earlier wrong codes stay locked.
        """
        today = today_local()
        if _daily_pickup_failures(db, delivery_boy_id, today) >= PICKUP_CODE_DAILY_FAILURE_LIMIT:
            raise DomainError("Too many wrong pickup codes today. Please contact Orleeno support.", 429,
                              code="PICKUP_VERIFICATION_BLOCKED")

        candidates = []
        for kind, model, day_col in (("subscription", Order, Order.order_date), ("extra", ExtraOrder, ExtraOrder.delivery_date)):
            rows = db.query(model).filter(
                model.delivery_boy_reference_id == delivery_boy_id,
                model.vendor_reference_id == provider_id,
                day_col == today,
                model.status.in_(PICKUP_READY_STATUSES),
            ).with_for_update().all()
            candidates += [(kind, o) for o in rows if not _pickup_locked(o)]
        if not candidates:
            raise DomainError("Nothing is ready for you at this kitchen right now", 404, code="NOTHING_READY")

        code_row = pickup_code_row(db, provider_id, today)
        usable = pickup_code_usable(code_row, today)
        if not usable or not matches(pickup_code, pickup_code_value(code_row)):
            kind, first = candidates[0]
            first.pickup_code_attempts = (first.pickup_code_attempts or 0) + 1
            _audit_verification(db, first, kind, "pickup", "failed", delivery_boy_id, ip,
                                reason="code_expired" if not usable else "wrong_code")
            db.commit()
            security_event("delivery.pickup_code_failed", order=order_ref(first), kind="bulk",
                           delivery_boy_id=delivery_boy_id, attempts=first.pickup_code_attempts)
            raise DomainError("Invalid pickup code. Please ask the kitchen for today's pickup code.",
                              code="INVALID_PICKUP_CODE")

        picked = []
        for kind, order in candidates:
            _assert(kind, order.status, "picked_up")
            order.status = "picked_up"
            order.picked_up_at = now_utc()
            _audit_verification(db, order, kind, "pickup", "success", delivery_boy_id, ip)
            picked.append({"order_id": order_ref(order), "kind": kind, "meal_slot": order.meal_slot})
        db.commit()
        business_event("order.bulk_picked_up", provider_id=provider_id, delivery_boy_id=delivery_boy_id,
                       orders=len(picked))
        return {"success": True, "message": f"{len(picked)} order(s) picked up", "picked_up": picked}

