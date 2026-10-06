"""
A one-time checkout is ONE delivery.

A checkout with several packages is stored as one extra_orders row per
package (its lines share checkout_id), so each line keeps its own price,
refund and kitchen decision. Everything about the trip is per checkout:

  * one delivery code for the customer (lines share the code seed; the code
    is derived from the checkout, see verification.delivery_code);
  * the lines are assigned to the same partner, picked up, started, marked
    arrived and delivered together;
  * the trip charges and the partner payout are priced on the first line only
    and the partner is paid once per checkout (orders.settle_extra_order).

Older checkouts (before this rule) keep their per-line codes and are still
paid once per checkout.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import DELIVERY_BOY_FEE_PER_DELIVERY
from app.domain.pricing import ZERO, money
from app.models.extra_order_model import ExtraOrder

# Seeds of codes shared by a whole checkout carry this prefix
SHARED_SEED_PREFIX = "c:"


def key(order: ExtraOrder) -> str:
    """Identity of the delivery an order line belongs to."""
    return str(order.checkout_id or order.extra_order_id)


def siblings(db: Session, order: ExtraOrder, *, statuses=None, delivery_boy_id=None, lock: bool = True) -> list:
    """The other lines of this order's checkout (optionally filtered), locked for update."""
    if order.checkout_id is None:
        return []
    q = db.query(ExtraOrder).filter(
        ExtraOrder.checkout_id == order.checkout_id,
        ExtraOrder.extra_order_id != order.extra_order_id,
    )
    if statuses is not None:
        q = q.filter(ExtraOrder.status.in_(tuple(statuses)))
    if delivery_boy_id is not None:
        q = q.filter(ExtraOrder.delivery_boy_reference_id == delivery_boy_id)
    if lock:
        q = q.with_for_update()
    return q.order_by(ExtraOrder.extra_order_id).all()


def lines(db: Session, order: ExtraOrder) -> list:
    """Every line of the checkout, this one included (no lock)."""
    if order.checkout_id is None:
        return [order]
    return db.query(ExtraOrder).filter(ExtraOrder.checkout_id == order.checkout_id).all()


def partner_payout(db: Session, order: ExtraOrder) -> Decimal:
    """
    What the partner earns for the whole trip. New checkouts carry it on one
    line; older ones priced it on every line, so the largest value is taken,
    never the sum. Orders from before pricing snapshots use the flat fee.
    """
    amounts = []
    for line in lines(db, order):
        settlement = (line.pricing_snapshot or {}).get("settlement")
        if settlement:
            amounts.append(Decimal(settlement.get("partner_payout_total") or "0"))
        else:
            amounts.append(money(DELIVERY_BOY_FEE_PER_DELIVERY))
    return max(amounts, default=ZERO)
