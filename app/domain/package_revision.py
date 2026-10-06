"""
Edits to a live package.

A kitchen's change to anything customers rely on (name, description, meal or
food type, prices, subscription availability, the item list) must be
reviewed. While the package is approved and on sale, the change is kept as a
pending revision on the package (`pending_changes`) and the approved version
stays on sale; an admin approval swaps the revision in, a rejection discards
it. Packages that are not live yet (pending / rejected) are edited directly.

pending_changes = {
    "fields": {field: value, ...},                  # only fields that differ
    "items": [{item_id, item_name, quantity, item_order}, ...],  # full new list, if changed
}
"""

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.errors import DomainError
from app.models.menu_package_item_model import MenuPackageItem
from app.models.menu_package_model import MenuPackage

PRICE_FIELDS = ("price", "discounted_price", "subscription_price")
MAX_ITEMS = 50


def is_live(package: MenuPackage) -> bool:
    return package.approval_status == "approved" and package.deleted_at is None


def _jsonable(value):
    return str(value) if isinstance(value, Decimal) else value


def _value(field: str, raw):
    if field in PRICE_FIELDS and raw is not None:
        return Decimal(str(raw))
    return raw


def _store(package: MenuPackage, pending: dict) -> None:
    pending = {k: v for k, v in pending.items() if v}
    package.pending_changes = pending or None
    package.pending_changes_at = now_utc() if pending else None


def proposed(package: MenuPackage, field: str):
    """The value a field will have once the pending revision is approved."""
    fields = (package.pending_changes or {}).get("fields", {})
    return _value(field, fields[field]) if field in fields else getattr(package, field)


def propose_fields(package: MenuPackage, changes: dict) -> bool:
    """Record field changes for review. Returns True if a revision is now pending."""
    pending = dict(package.pending_changes or {})
    fields = dict(pending.get("fields", {}))
    for field, value in changes.items():
        if _value(field, value) == getattr(package, field):
            fields.pop(field, None)  # back to the live value: nothing to review
        else:
            fields[field] = _jsonable(value)
    pending["fields"] = fields
    _store(package, pending)
    return package.pending_changes is not None


def live_items(package: MenuPackage) -> list[dict]:
    return [
        {"item_id": str(i.item_id), "item_name": i.item_name, "quantity": i.quantity, "item_order": i.item_order}
        for i in sorted(package.items, key=lambda i: i.item_order or 0)
    ]


def editable_items(package: MenuPackage) -> list[dict]:
    """The item list being edited: the pending one, or a copy of the live one."""
    pending = (package.pending_changes or {}).get("items")
    return [dict(i) for i in (pending if pending is not None else live_items(package))]


def propose_items(package: MenuPackage, items: list[dict]) -> None:
    if not items:
        raise DomainError("A package must keep at least one item")
    if len(items) > MAX_ITEMS:
        raise DomainError(f"A package can have at most {MAX_ITEMS} items")
    pending = dict(package.pending_changes or {})
    pending["items"] = None if items == live_items(package) else items
    _store(package, pending)


def new_item(item_name: str, quantity, item_order: int) -> dict:
    return {"item_id": str(uuid.uuid4()), "item_name": item_name, "quantity": quantity, "item_order": item_order}


def find_item(package: MenuPackage, item_id) -> dict | None:
    return next((i for i in editable_items(package) if i["item_id"] == str(item_id)), None)


def apply(db: Session, package: MenuPackage) -> None:
    """Admin approved the revision: it becomes the live version."""
    pending = package.pending_changes or {}
    for field, raw in pending.get("fields", {}).items():
        setattr(package, field, _value(field, raw))
    items = pending.get("items")
    if items is not None:
        for live in list(package.items):
            db.delete(live)
        db.flush()
        for i in items:
            db.add(MenuPackageItem(
                item_id=uuid.UUID(i["item_id"]), package_reference_id=package.package_id,
                item_name=i["item_name"], quantity=i["quantity"], item_order=i["item_order"],
            ))
    discard(package)
    db.flush()
    db.expire(package, ["items"])


def discard(package: MenuPackage) -> None:
    package.pending_changes = None
    package.pending_changes_at = None


def view(package: MenuPackage) -> dict | None:
    if not package.pending_changes:
        return None
    return {**package.pending_changes, "submitted_at": package.pending_changes_at}
