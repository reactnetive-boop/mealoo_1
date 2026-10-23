"""
Read-only review of delivery partner payouts (wallet credits per delivery).

Nothing here changes data. It answers, for the whole history:

  duplicate_payouts         one delivery (subscription meal, or one-time
                            checkout = one trip) credited more than once
  delivered_without_payout  a completed delivery with a partner that was
                            never credited
  paid_but_not_delivered    a credit for a delivery that is not 'delivered'
                            (before 2026-10-24 a failed hand-over also paid
                            the partner; such credits are listed for review)
  differs_from_current_rate credits whose amount is not today's configured
                            payout (expected after an admin changes it)

Corrections are a business decision: an admin reviews the list and posts a
wallet adjustment with a note (Admin -> Delivery partner -> Wallet), so the
ledger keeps both the original credit and the correction. Balances are never
rewritten automatically.

Used by the nightly reconciliation (app.domain.maintenance) and by
scripts/reconcile_partner_payouts.py.
"""

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.pricing import PARTNER_PAYOUT_KEY, current_components, money
from app.models.delivery_boy_wallet_transaction_model import DeliveryBoyWalletTransaction as Txn
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order

SAMPLE = 20


def _rows(items, sample: int | None):
    return items if sample is None else items[:sample]


def review(db: Session, sample: int | None = SAMPLE) -> dict:
    payouts = db.query(Txn).filter(Txn.reason == "delivery_payout", Txn.type == "credit").all()

    sub_ids = {t.reference_id for t in payouts if t.reference_type == "order" and t.reference_id}
    extra_ids = {t.reference_id for t in payouts if t.reference_type == "extra_order" and t.reference_id}
    meals = {o.order_id: o for o in db.query(Order).filter(Order.order_id.in_(sub_ids))} if sub_ids else {}
    lines = (
        {o.extra_order_id: o for o in db.query(ExtraOrder).filter(ExtraOrder.extra_order_id.in_(extra_ids))}
        if extra_ids else {}
    )

    def trip_of(txn) -> str:
        line = lines.get(txn.reference_id)
        return str((line.checkout_id or line.extra_order_id) if line else txn.reference_id)

    by_delivery: dict = {}
    for t in payouts:
        key = ("order", str(t.reference_id)) if t.reference_type == "order" else ("trip", trip_of(t))
        by_delivery.setdefault(key, []).append(t)

    duplicates = [
        {
            "delivery": f"{kind}:{ref}",
            "delivery_boy_id": str(txns[0].delivery_boy_reference_id),
            "credits": len(txns),
            "total": str(sum((money(t.amount) for t in txns), Decimal("0"))),
            "transaction_ids": [str(t.delivery_boy_wallet_transaction_id) for t in txns],
        }
        for (kind, ref), txns in by_delivery.items() if len(txns) > 1
    ]

    paid_not_delivered = []
    for t in payouts:
        order = meals.get(t.reference_id) if t.reference_type == "order" else lines.get(t.reference_id)
        status = order.status if order is not None else "missing"
        if status != "delivered":
            paid_not_delivered.append({
                "transaction_id": str(t.delivery_boy_wallet_transaction_id),
                "delivery_boy_id": str(t.delivery_boy_reference_id),
                "reference_type": t.reference_type,
                "reference_id": str(t.reference_id) if t.reference_id else None,
                "order_status": status,
                "amount": str(money(t.amount)),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

    paid_meals = {ref for kind, ref in by_delivery if kind == "order"}
    paid_trips = {ref for kind, ref in by_delivery if kind == "trip"}
    unpaid_meals = [
        str(oid) for (oid,) in db.query(Order.order_id).filter(
            Order.status == "delivered", Order.delivery_boy_reference_id.isnot(None),
        )
        if str(oid) not in paid_meals
    ]
    trip_key = func.coalesce(ExtraOrder.checkout_id, ExtraOrder.extra_order_id)
    unpaid_trips = [
        str(trip) for (trip,) in db.query(trip_key).filter(
            ExtraOrder.status == "delivered", ExtraOrder.delivery_boy_reference_id.isnot(None),
        ).distinct()
        if str(trip) not in paid_trips
    ]

    component = next((c for c in current_components(db) if c.component_key == PARTNER_PAYOUT_KEY), None)
    current_fixed = (
        money(component.value)
        if component is not None and component.is_active and component.calc_type == "fixed"
        and component.charge_basis in ("per_delivery", "per_order")
        else None
    )
    differs = (
        sum(1 for t in payouts if money(t.amount) != current_fixed) if current_fixed is not None else None
    )

    return {
        "payout_setting": {
            "component_key": PARTNER_PAYOUT_KEY,
            "value": str(money(component.value)) if component is not None else None,
            "calc_type": component.calc_type if component is not None else None,
            "charge_basis": component.charge_basis if component is not None else None,
            "is_active": bool(component.is_active) if component is not None else False,
            "version": component.version if component is not None else None,
        },
        "payouts": {
            "count": len(payouts),
            "total": str(sum((money(t.amount) for t in payouts), Decimal("0"))),
        },
        "duplicate_payouts": {"count": len(duplicates), "sample": _rows(duplicates, sample)},
        "delivered_without_payout": {
            "count": len(unpaid_meals) + len(unpaid_trips),
            "sample": _rows([f"order:{i}" for i in unpaid_meals] + [f"trip:{i}" for i in unpaid_trips], sample),
        },
        "paid_but_not_delivered": {"count": len(paid_not_delivered), "sample": _rows(paid_not_delivered, sample)},
        "differs_from_current_rate": {"count": differs},
    }
