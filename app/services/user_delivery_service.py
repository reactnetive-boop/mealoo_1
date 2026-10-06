"""
Customer view of today's deliveries: every subscription meal and one-time
order arriving today, with the delivery code to read out to the partner.

The code is only returned to its own customer, only on the delivery day and
only while the order is open (it disappears once delivered).
"""

from collections import defaultdict

from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.domain.slots import SLOTS
from app.domain.status import SUB_OPEN_STATUSES, EXTRA_OPEN_STATUSES
from app.domain.verification import delivery_code, delivery_code_expired
from app.models.delivery_boy_model import DeliveryBoy
from app.models.extra_order_model import ExtraOrder
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.subscription_package_model import SubscriptionPackage

_SLOT_RANK = {slot: i for i, slot in enumerate(SLOTS)}


def _lookup(db: Session, model, key: str, ids) -> dict:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {getattr(r, key): r for r in db.query(model).filter(getattr(model, key).in_(ids))}


def _first_name(name: str | None) -> str | None:
    return name.split()[0] if name else None


class UserDeliveryService:

    @staticmethod
    def today(db: Session, user_id: str) -> dict:
        today = today_local()
        meals = db.query(Order).filter(
            Order.user_reference_id == user_id,
            Order.order_date == today,
            Order.status.in_(SUB_OPEN_STATUSES + ("delivered",)),
        ).all()
        extras = db.query(ExtraOrder).filter(
            ExtraOrder.user_reference_id == user_id,
            ExtraOrder.delivery_date == today,
            ExtraOrder.status.in_(EXTRA_OPEN_STATUSES + ("delivered",)),
        ).all()

        kitchens = _lookup(db, Provider, "provider_id", [o.vendor_reference_id for o in meals + extras])
        partners = _lookup(db, DeliveryBoy, "delivery_boy_id", [o.delivery_boy_reference_id for o in meals + extras])
        packages = _lookup(db, MenuPackage, "package_id", [o.package_reference_id for o in extras])
        sub_items = defaultdict(list)
        sub_ids = {o.subscription_reference_id for o in meals}
        if sub_ids:
            for sp, mp in (
                db.query(SubscriptionPackage, MenuPackage)
                .join(MenuPackage, MenuPackage.package_id == SubscriptionPackage.package_reference_id)
                .filter(SubscriptionPackage.subscription_reference_id.in_(sub_ids))
            ):
                sub_items[sp.subscription_reference_id].append({"package_name": mp.package_name, "quantity": sp.quantity})

        def common(o, open_statuses) -> dict:
            kitchen = kitchens.get(o.vendor_reference_id)
            partner = partners.get(o.delivery_boy_reference_id)
            show_code = o.status in open_statuses and not delivery_code_expired(o)
            return {
                "meal_slot": o.meal_slot,
                "status": o.status,
                "vendor_name": kitchen.business_name if kitchen else None,
                "delivery_partner_name": _first_name(partner.full_name) if partner else None,
                "delivery_code": delivery_code(o) if show_code else None,
                "picked_up_at": o.picked_up_at,
                "out_for_delivery_at": o.out_for_delivery_at,
                "arrived_at": o.arrived_at,
                "delivered_at": o.delivered_at,
            }

        rows = [
            {
                "kind": "subscription",
                "order_id": o.order_id,
                "subscription_id": o.subscription_reference_id,
                "items": sub_items.get(o.subscription_reference_id, []),
                **common(o, SUB_OPEN_STATUSES),
            }
            for o in meals
        ] + [
            {
                "kind": "extra",
                "order_id": o.extra_order_id,
                "subscription_id": None,
                "items": [{
                    "package_name": packages[o.package_reference_id].package_name if o.package_reference_id in packages else None,
                    "quantity": o.quantity,
                }],
                **common(o, EXTRA_OPEN_STATUSES),
            }
            for o in extras
        ]
        rows.sort(key=lambda r: (r["status"] == "delivered", _SLOT_RANK.get(r["meal_slot"], 9)))
        return {"success": True, "date": today, "total": len(rows), "deliveries": rows}
