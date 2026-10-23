"""
A one-time checkout is ONE delivery.

A checkout with several packages is stored as one extra_orders row per
package (its lines share checkout_id), so each line keeps its own price,
refund and kitchen decision. Everything about the trip is per checkout:

  * one delivery code for the customer (lines share the code seed; the code
    is derived from the checkout, see verification.delivery_code);
  * the lines are assigned to the same partner, picked up, started, marked
    arrived and delivered together;
  * the trip charges are priced on the first line only and the partner is
    paid once per checkout, at the payout configured when it is delivered
    (orders.settle_extra_order).

Older checkouts (before this rule) keep their per-line codes and are still
paid once per checkout.
"""

from sqlalchemy.orm import Session

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
