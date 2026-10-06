"""
Order / subscription state machines.

Every status change goes through `assert_transition`, which knows which
actor may move an order from which status to which. Anything not listed is
rejected, so no client can set an arbitrary status.

Hand-over chain for both order kinds:

    ... -> preparing -> ready_for_pickup -> picked_up -> out_for_delivery -> delivered
           (kitchen)    (kitchen, optional)  (partner +     (partner,          (partner +
                                              kitchen's      "start delivery")  customer's
                                              daily code)                       order code)

Pickup and delivery verification are actions, not stored statuses: the code
is checked and the status moves in the same locked transaction.
"""

from app.core.errors import DomainError

# ── Subscription meals (subscription.orders) ──────────────────
SUB_ORDER_STATUSES = (
    "scheduled", "preparing", "ready_for_pickup", "picked_up", "out_for_delivery",
    "delivered", "delivery_failed", "skipped", "cancelled",
)

# ── One-time orders (subscription.extra_orders) ───────────────
EXTRA_ORDER_STATUSES = (
    "pending", "confirmed", "preparing", "ready_for_pickup", "picked_up", "out_for_delivery",
    "delivered", "delivery_failed", "cancelled",
)

# delivery_failed: the partner reached the address but could not hand over
TERMINAL_ORDER_STATUSES = ("delivered", "delivery_failed", "skipped", "cancelled")

# Still at the kitchen: a partner can be (re)assigned and nothing has moved yet
SUB_UNPICKED_STATUSES = ("scheduled", "preparing", "ready_for_pickup")
EXTRA_UNPICKED_STATUSES = ("pending", "confirmed", "preparing", "ready_for_pickup")

# The kitchen has handed the food to this partner
IN_HAND_STATUSES = ("picked_up", "out_for_delivery")

# The partner may verify pickup from these
PICKUP_READY_STATUSES = ("preparing", "ready_for_pickup")

# Live orders count against capacity and show the customer's delivery code
SUB_OPEN_STATUSES = SUB_UNPICKED_STATUSES + IN_HAND_STATUSES
EXTRA_OPEN_STATUSES = EXTRA_UNPICKED_STATUSES + IN_HAND_STATUSES

# ── Subscriptions ─────────────────────────────────────────────
SUBSCRIPTION_STATUSES = ("active", "paused", "cancelled", "switched", "expired")

# (from, to) -> actors allowed to make the move. "system" = jobs / domain code
# acting on behalf of another action (pause, cancel, holiday sweep).
_SUB_ORDER_TRANSITIONS: dict[tuple[str, str], set[str]] = {
    ("scheduled", "preparing"): {"provider"},
    ("preparing", "ready_for_pickup"): {"provider"},
    # pickup with the kitchen's daily code; marking "ready" is optional for the kitchen
    ("preparing", "picked_up"): {"delivery_boy"},
    ("ready_for_pickup", "picked_up"): {"delivery_boy"},
    ("picked_up", "out_for_delivery"): {"delivery_boy"},
    # delivery with the customer's code; from picked_up "start delivery" is implied
    ("out_for_delivery", "delivered"): {"delivery_boy", "admin"},
    ("picked_up", "delivered"): {"delivery_boy", "admin"},
    ("out_for_delivery", "delivery_failed"): {"delivery_boy", "admin"},
    ("picked_up", "delivery_failed"): {"delivery_boy", "admin"},
    # admin review of a failed delivery: refund it, or it was in fact received
    ("delivery_failed", "cancelled"): {"admin"},
    ("delivery_failed", "delivered"): {"admin"},
    ("scheduled", "skipped"): {"customer"},
    ("scheduled", "cancelled"): {"system", "admin"},
    ("preparing", "cancelled"): {"admin"},
    ("ready_for_pickup", "cancelled"): {"admin"},
    ("picked_up", "cancelled"): {"admin"},
    ("out_for_delivery", "cancelled"): {"admin"},
    # restore meals cancelled by a pause
    ("cancelled", "scheduled"): {"system"},
    # admin corrections for stuck orders (super admin only, audited)
    ("scheduled", "delivered"): {"admin"},
    ("preparing", "delivered"): {"admin"},
    ("ready_for_pickup", "delivered"): {"admin"},
    ("preparing", "scheduled"): {"admin"},
    ("ready_for_pickup", "preparing"): {"admin"},
    ("picked_up", "ready_for_pickup"): {"admin"},
    ("out_for_delivery", "ready_for_pickup"): {"admin"},
    ("out_for_delivery", "preparing"): {"admin"},
}

_EXTRA_ORDER_TRANSITIONS: dict[tuple[str, str], set[str]] = {
    ("pending", "confirmed"): {"provider"},
    ("pending", "cancelled"): {"provider", "customer", "system", "admin"},
    ("confirmed", "preparing"): {"provider"},
    ("preparing", "ready_for_pickup"): {"provider"},
    ("confirmed", "cancelled"): {"system", "admin"},
    ("preparing", "picked_up"): {"delivery_boy"},
    ("ready_for_pickup", "picked_up"): {"delivery_boy"},
    ("picked_up", "out_for_delivery"): {"delivery_boy"},
    ("out_for_delivery", "delivered"): {"delivery_boy", "admin"},
    ("picked_up", "delivered"): {"delivery_boy", "admin"},
    ("out_for_delivery", "delivery_failed"): {"delivery_boy", "admin"},
    ("picked_up", "delivery_failed"): {"delivery_boy", "admin"},
    ("delivery_failed", "cancelled"): {"admin"},
    ("delivery_failed", "delivered"): {"admin"},
    ("preparing", "cancelled"): {"admin"},
    ("ready_for_pickup", "cancelled"): {"admin"},
    ("picked_up", "cancelled"): {"admin"},
    ("out_for_delivery", "cancelled"): {"admin"},
    ("confirmed", "delivered"): {"admin"},
    ("preparing", "delivered"): {"admin"},
    ("ready_for_pickup", "delivered"): {"admin"},
    ("preparing", "confirmed"): {"admin"},
    ("ready_for_pickup", "preparing"): {"admin"},
    ("picked_up", "ready_for_pickup"): {"admin"},
    ("out_for_delivery", "ready_for_pickup"): {"admin"},
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
