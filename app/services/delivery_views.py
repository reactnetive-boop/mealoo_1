"""Read models of the delivery partner app: order rows, cards, statuses and lookups."""

from datetime import date

from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.core.config import (
    DELIVERY_CODE_MAX_ATTEMPTS,
    PICKUP_CODE_MAX_ATTEMPTS,
)
from app.core.errors import DomainError
from app.domain.slots import SLOTS, delivery_window
from app.domain.status import (
    IN_HAND_STATUSES,
)
from app.domain.verification import (
    order_day,
)
from app.models.extra_order_model import ExtraOrder
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.user_address_model import UserAddress
from app.models.user_model import User

HISTORY_MAX_DAYS = 31
_SLOT_RANK = {slot: i for i, slot in enumerate(SLOTS)}


def _date_window(on: date | None, from_date: date | None, to_date: date | None) -> tuple[date, date]:
    if on is not None:
        return on, on
    start = from_date or today_local()
    end = to_date or start
    if end < start:
        raise DomainError("to_date is before from_date")
    if (end - start).days > HISTORY_MAX_DAYS:
        raise DomainError(f"History is limited to {HISTORY_MAX_DAYS} days per request")
    return start, end


def _sort_key(row: dict):
    return (row["date"], _SLOT_RANK.get(row["meal_slot"], 9))


def _lookup(db: Session, model, key: str, ids) -> dict:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {getattr(r, key): r for r in db.query(model).filter(getattr(model, key).in_(ids))}


def _short_address(a: UserAddress | None) -> str | None:
    if a is None:
        return None
    return ", ".join(p for p in (a.address_line1, a.address_line2, a.city, a.pin_code) if p)


def _kitchen_address(p: Provider | None) -> str | None:
    if p is None:
        return None
    return ", ".join(str(x) for x in (p.house_no, p.address, p.area, p.city, p.pincode) if x)


def _pickup_locked(o) -> bool:
    return (o.pickup_code_attempts or 0) >= PICKUP_CODE_MAX_ATTEMPTS


def _delivery_locked(o) -> bool:
    return (o.delivery_code_attempts or 0) >= DELIVERY_CODE_MAX_ATTEMPTS


def _pickup_status(o) -> str:
    if o.status in ("cancelled", "skipped"):
        return "cancelled"
    if o.status in IN_HAND_STATUSES or o.status == "delivered":
        return "picked_up"
    if _pickup_locked(o):
        return "locked"
    if o.status == "ready_for_pickup":
        return "ready"
    if o.status == "preparing":
        return "preparing"
    return "not_started"


def _delivery_status(o) -> str:
    if o.status in ("cancelled", "skipped"):
        return o.status
    if o.status == "delivered":
        return "delivered"
    if _delivery_locked(o):
        return "failed"
    if o.status == "out_for_delivery":
        return "on_the_way"
    if o.status == "picked_up":
        return "picked_up"
    return "pending"


class _Lookups:
    """Names / addresses for a batch of orders, fetched in a few queries."""

    def __init__(self, db: Session, subs: list[Order], extras: list[ExtraOrder]):
        everything = list(subs) + list(extras)
        self.kitchens = _lookup(db, Provider, "provider_id", (o.vendor_reference_id for o in everything))
        self.users = _lookup(db, User, "user_id", (o.user_reference_id for o in everything))
        self.addresses = _lookup(
            db, UserAddress, "user_address_id",
            [o.delivery_address_reference_id for o in subs] + [o.address_reference_id for o in extras],
        )
        self.packages = _lookup(db, MenuPackage, "package_id", (o.package_reference_id for o in extras))


def _common(o, address_id, lk: _Lookups) -> dict:
    kitchen = lk.kitchens.get(o.vendor_reference_id)
    user = lk.users.get(o.user_reference_id)
    address = lk.addresses.get(address_id)
    return {
        "vendor_name": kitchen.business_name if kitchen else None,
        "vendor_address": _kitchen_address(kitchen),
        "customer_name": user.full_name if user else None,
        "delivery_area": f"{address.city} {address.pin_code}" if address else None,
        "delivery_address_short": _short_address(address),
        "pickup_status": _pickup_status(o),
        "delivery_status": _delivery_status(o),
        "pickup_locked": _pickup_locked(o),
        "delivery_locked": _delivery_locked(o),
        "picked_up_at": o.picked_up_at,
        "out_for_delivery_at": o.out_for_delivery_at,
        "arrived_at": o.arrived_at,
        "delivered_at": o.delivered_at,
        "delivery_window": delivery_window(o.meal_slot),
    }


def _sub_view(o: Order, lk: _Lookups | None = None) -> dict:
    view = {
        "order_id": o.order_id,
        "subscription_reference_id": o.subscription_reference_id,
        "user_reference_id": o.user_reference_id,
        "vendor_reference_id": o.vendor_reference_id,
        "order_date": o.order_date,
        "meal_slot": o.meal_slot,
        "status": o.status,
        "is_free_skip": o.is_free_skip,
        "delivery_notes": o.delivery_notes,
        "created_at": o.created_at,
    }
    if lk is not None:
        view.update(_common(o, o.delivery_address_reference_id, lk))
    else:
        view.update({
            "pickup_status": _pickup_status(o), "delivery_status": _delivery_status(o),
            "pickup_locked": _pickup_locked(o), "delivery_locked": _delivery_locked(o),
            "picked_up_at": o.picked_up_at, "out_for_delivery_at": o.out_for_delivery_at,
            "arrived_at": o.arrived_at, "delivered_at": o.delivered_at,
        })
    return view


def _extra_view(o: ExtraOrder, lk: _Lookups | None = None) -> dict:
    view = {
        "extra_order_id": o.extra_order_id,
        "user_reference_id": o.user_reference_id,
        "vendor_reference_id": o.vendor_reference_id,
        "package_reference_id": o.package_reference_id,
        "quantity": o.quantity,
        "unit_price": o.unit_price,
        "total_price": o.total_price,
        "delivery_date": o.delivery_date,
        "meal_slot": o.meal_slot,
        "status": o.status,
        "created_at": o.created_at,
    }
    if lk is not None:
        view.update(_common(o, o.address_reference_id, lk))
        pkg = lk.packages.get(o.package_reference_id)
        view["package_name"] = pkg.package_name if pkg else None
    else:
        view.update({
            "pickup_status": _pickup_status(o), "delivery_status": _delivery_status(o),
            "pickup_locked": _pickup_locked(o), "delivery_locked": _delivery_locked(o),
            "picked_up_at": o.picked_up_at, "out_for_delivery_at": o.out_for_delivery_at,
            "arrived_at": o.arrived_at, "delivered_at": o.delivered_at,
        })
    return view


def _card(o, kind: str, lk: _Lookups) -> dict:
    """Uniform shape for both order kinds (dashboard, subscription detail)."""
    is_sub = kind == "subscription"
    card = {
        "kind": kind,
        "order_id": o.order_id if is_sub else o.extra_order_id,
        "subscription_id": o.subscription_reference_id if is_sub else None,
        "date": order_day(o),
        "meal_slot": o.meal_slot,
        "status": o.status,
        **_common(o, o.delivery_address_reference_id if is_sub else o.address_reference_id, lk),
    }
    if not is_sub:
        pkg = lk.packages.get(o.package_reference_id)
        card["package_name"] = pkg.package_name if pkg else None
        card["quantity"] = o.quantity
    return card


