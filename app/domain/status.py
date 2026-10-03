"""
Order / subscription state machines.

Every status change goes through `assert_transition`, which knows which
actor may move an order from which status to which. Anything not listed is
rejected, so no client can set an arbitrary status.
"""

from app.core.errors import DomainError

# ── Subscription meals (subscription.orders) ──────────────────
SUB_ORDER_STATUSES = ("scheduled", "preparing", "out_for_delivery", "delivered", "skipped", "cancelled")

# ── One-time orders (subscription.extra_orders) ───────────────
EXTRA_ORDER_STATUSES = ("pending", "confirmed", "preparing", "out_for_delivery", "delivered", "cancelled")

TERMINAL_ORDER_STATUSES = ("delivered", "skipped", "cancelled")

# ── Subscriptions ─────────────────────────────────────────────
SUBSCRIPTION_STATUSES = ("active", "paused", "cancelled", "switched", "expired")

# (from, to) -> actors allowed to make the move. "system" = jobs / domain code
# acting on behalf of another action (pause, cancel, holiday sweep).
_SUB_ORDER_TRANSITIONS: dict[tuple[str, str], set[str]] = {
    ("scheduled", "preparing"): {"provider"},
    ("preparing", "out_for_delivery"): {"delivery_boy"},
    ("scheduled", "skipped"): {"customer"},
    ("scheduled", "cancelled"): {"system", "admin"},
    ("preparing", "cancelled"): {"admin"},
    ("out_for_delivery", "cancelled"): {"admin"},
    # restore meals cancelled by a pause
    ("cancelled", "scheduled"): {"system"},
    # admin corrections for stuck orders (super admin only, audited)
    ("scheduled", "delivered"): {"admin"},
    ("preparing", "delivered"): {"admin"},
    ("out_for_delivery", "delivered"): {"delivery_boy", "admin"},
    ("preparing", "scheduled"): {"admin"},
    ("out_for_delivery", "preparing"): {"admin"},
}

_EXTRA_ORDER_TRANSITIONS: dict[tuple[str, str], set[str]] = {
    ("pending", "confirmed"): {"provider"},
    ("pending", "cancelled"): {"provider", "customer", "system", "admin"},
    ("confirmed", "preparing"): {"provider"},
    ("confirmed", "cancelled"): {"system", "admin"},
    ("preparing", "out_for_delivery"): {"delivery_boy"},
    ("out_for_delivery", "delivered"): {"delivery_boy", "admin"},
    ("preparing", "cancelled"): {"admin"},
    ("out_for_delivery", "cancelled"): {"admin"},
    ("confirmed", "delivered"): {"admin"},
    ("preparing", "delivered"): {"admin"},
    ("preparing", "confirmed"): {"admin"},
    ("out_for_delivery", "preparing"): {"admin"},
}


def _check(table, kind: str, current: str, target: str, actor: str) -> None:
    if current == target:
        raise DomainError(f"Order is already {current.replace('_', ' ')}", 409)
    allowed = table.get((current, target))
    if not allowed or actor not in allowed:
        raise DomainError(f"A {kind} cannot move from '{current}' to '{target}'", 400)


def assert_sub_order_transition(current: str, target: str, actor: str) -> None:
    if target not in SUB_ORDER_STATUSES:
        raise DomainError(f"Invalid status '{target}'", 400)
    _check(_SUB_ORDER_TRANSITIONS, "subscription meal", current, target, actor)


def assert_extra_order_transition(current: str, target: str, actor: str) -> None:
    if target not in EXTRA_ORDER_STATUSES:
        raise DomainError(f"Invalid status '{target}'", 400)
    _check(_EXTRA_ORDER_TRANSITIONS, "one-time order", current, target, actor)


def allowed_next(kind: str, current: str, actor: str) -> list[str]:
    table = _SUB_ORDER_TRANSITIONS if kind == "subscription" else _EXTRA_ORDER_TRANSITIONS
    return [to for (frm, to), actors in table.items() if frm == current and actor in actors]
