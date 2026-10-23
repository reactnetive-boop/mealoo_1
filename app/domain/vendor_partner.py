"""
Kitchens a delivery partner serves, and automatic assignment of their work.

Orleeno (admin) gives each kitchen one current delivery partner; one partner
can serve several kitchens (delivery.delivery_partner_vendors). The kitchen's
work then goes to that partner without an admin assigning every order:

  new subscription            -> the subscription is assigned to the partner;
                                 its meals follow (delivery_assignment)
  meals generated later       -> inherit the subscription's partner; a
  (midnight job, resume,         subscription still without a usable partner
  switch)                        is given the kitchen's partner
  new one-time order          -> every line of the checkout goes to the partner
  order / subscription moved  -> the new kitchen's partner (admin holiday cover,
  to another kitchen             kitchen transfer)

A kitchen without a partner, or whose partner is deactivated, not approved or
on leave that day, keeps the work unassigned; admin lists and the dashboard
flag it. Work is never handed to an unrelated partner. Every step is
idempotent: running it again (job retries, API retries) finds the work
already assigned and changes nothing.

Changing a kitchen's partner (caller's transaction, rows locked):

  assign kitchen to P (none before)  -> its open unassigned work goes to P
  move kitchen from A to B           -> work A has not picked up moves to B,
                                        what A carries stays with A, delivered
                                        and past work is untouched
  remove kitchen from P              -> P's open work for it is unassigned and
                                        flagged; P's other kitchens untouched

A partner with kitchens serves only those kitchens; a partner with none is in
the shared pool and can still be given single subscriptions or orders by hand.
"""

import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import record_audit, business_event
from app.core.clock import now_utc, today_local
from app.core.errors import DomainError
from app.domain import checkout, delivery_assignment, notify, partner_leave
from app.domain.status import EXTRA_UNPICKED_STATUSES, IN_HAND_STATUSES, SUB_UNPICKED_STATUSES
from app.models.delivery_boy_model import DeliveryBoy
from app.models.delivery_partner_vendor_model import DeliveryPartnerVendor
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.subscription_model import Subscription

AUTO_NOTE = "Kitchen's delivery partner (automatic)"


# ── Queries ───────────────────────────────────────────────────

def partner_rows(db: Session, delivery_boy_id, lock: bool = False) -> list[DeliveryPartnerVendor]:
    q = db.query(DeliveryPartnerVendor).filter(
        DeliveryPartnerVendor.delivery_boy_reference_id == delivery_boy_id,
        DeliveryPartnerVendor.status == "active",
    )
    if lock:
        q = q.with_for_update()
    return q.order_by(DeliveryPartnerVendor.assigned_at.asc()).all()


def vendor_ids(db: Session, delivery_boy_id) -> set[str]:
    """Kitchens this partner currently serves (empty = shared pool)."""
    rows = db.query(DeliveryPartnerVendor.provider_reference_id).filter(
        DeliveryPartnerVendor.delivery_boy_reference_id == delivery_boy_id,
        DeliveryPartnerVendor.status == "active",
    ).all()
    return {str(r[0]) for r in rows}


def serves(db: Session, delivery_boy_id, provider_id) -> bool:
    """A partner can take this kitchen's work: it is one of their kitchens, or they are in the pool."""
    ids = vendor_ids(db, delivery_boy_id)
    return not ids or str(provider_id) in ids


def kitchen_row(db: Session, provider_id, lock: bool = False) -> DeliveryPartnerVendor | None:
    q = db.query(DeliveryPartnerVendor).filter(
        DeliveryPartnerVendor.provider_reference_id == provider_id,
        DeliveryPartnerVendor.status == "active",
    )
    if lock:
        q = q.with_for_update()
    return q.first()


def usable(boy: DeliveryBoy | None) -> bool:
    return boy is not None and bool(boy.is_active) and boy.approval_status == "approved"


def kitchen_partner(db: Session, provider_id) -> DeliveryBoy | None:
    """The kitchen's current partner, if they can take work right now (active and approved)."""
    row = kitchen_row(db, provider_id)
    if row is None:
        return None
    boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == row.delivery_boy_reference_id).first()
    return boy if usable(boy) else None


def partner_for(db: Session, provider_id, on: date):
    """Partner id new work of this kitchen on `on` goes to, or None (left unassigned, flagged)."""
    boy = kitchen_partner(db, provider_id)
    if boy is None or partner_leave.on_leave(db, boy.delivery_boy_id, on):
        return None
    return boy.delivery_boy_id


def partners_by_kitchen(db: Session, provider_ids) -> dict:
    """{provider_id: DeliveryBoy} of the current partners of these kitchens (one query)."""
    ids = {p for p in provider_ids if p is not None}
    if not ids:
        return {}
    rows = (
        db.query(DeliveryPartnerVendor.provider_reference_id, DeliveryBoy)
        .join(DeliveryBoy, DeliveryBoy.delivery_boy_id == DeliveryPartnerVendor.delivery_boy_reference_id)
        .filter(DeliveryPartnerVendor.provider_reference_id.in_(ids), DeliveryPartnerVendor.status == "active")
        .all()
    )
    return {pid: boy for pid, boy in rows}


def kitchens_by_partner(db: Session, delivery_boy_ids) -> dict:
    """{delivery_boy_id (UUID): [(row, Provider)]} of the partners' current kitchens (one query)."""
    ids = {b if isinstance(b, uuid.UUID) else uuid.UUID(str(b)) for b in delivery_boy_ids if b is not None}
    out: dict = {b: [] for b in ids}
    if not ids:
        return out
    rows = (
        db.query(DeliveryPartnerVendor, Provider)
        .join(Provider, Provider.provider_id == DeliveryPartnerVendor.provider_reference_id)
        .filter(DeliveryPartnerVendor.delivery_boy_reference_id.in_(ids), DeliveryPartnerVendor.status == "active")
        .order_by(DeliveryPartnerVendor.assigned_at.asc())
        .all()
    )
    for row, provider in rows:
        out.setdefault(row.delivery_boy_reference_id, []).append((row, provider))
    return out


def partner_kitchens(db: Session, delivery_boy_id) -> list:
    """[(row, Provider)] of one partner's current kitchens, oldest assignment first."""
    return next(iter(kitchens_by_partner(db, [delivery_boy_id]).values()), [])


def kitchen_address(p: Provider | None) -> str | None:
    if p is None:
        return None
    return ", ".join(str(x) for x in (p.house_no, p.address, p.area, p.landmark, p.city, p.state, p.pincode) if x)


# ── Automatic assignment of new work ──────────────────────────

def _lock_subscription(db: Session, sub: Subscription) -> None:
    # lock only: never reload, the caller may hold unflushed changes (autoflush is off)
    db.query(Subscription.subscription_id).filter(
        Subscription.subscription_id == sub.subscription_id
    ).with_for_update().scalar()


def ensure_subscription_partner(db: Session, sub: Subscription, *, quiet: bool = False) -> dict | None:
    """
    Give a running subscription its kitchen's partner when it has no usable
    partner of its own. An explicit (admin) assignment to a partner who can
    still serve the kitchen is respected. Safe to repeat.
    """
    if sub.status not in delivery_assignment.ASSIGNABLE_SUBSCRIPTION_STATUSES:
        return None
    if sub.delivery_boy_reference_id is not None and delivery_assignment.inherited_partner(db, sub) is not None:
        return None
    boy = kitchen_partner(db, sub.vendor_reference_id)
    if boy is None:
        return None
    _lock_subscription(db, sub)
    return delivery_assignment.assign(
        db, sub, boy, actor_id=None, actor_type="system", note=AUTO_NOTE, notify_parties=not quiet,
    )


def assign_checkout(db: Session, lines: list[ExtraOrder]) -> DeliveryBoy | None:
    """New one-time checkout: all its lines go to the kitchen's partner for that day (one trip)."""
    if not lines:
        return None
    first = lines[0]
    partner_id = partner_for(db, first.vendor_reference_id, first.delivery_date)
    if partner_id is None:
        return None
    for line in lines:
        if line.delivery_boy_reference_id is None:
            line.delivery_boy_reference_id = partner_id
    notify.delivery_partner(
        db, partner_id, "order_assigned", "New delivery assigned",
        f"One-time {first.meal_slot} delivery on {first.delivery_date}.",
        {"order_id": str(first.extra_order_id), "kind": "extra"},
    )
    return db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == partner_id).first()


def assign_moved_order(db: Session, order, kind: str) -> None:
    """An order an admin moved to another kitchen goes to that kitchen's partner (if any)."""
    on = order.order_date if kind == "subscription" else order.delivery_date
    partner_id = partner_for(db, order.vendor_reference_id, on)
    if partner_id is None:
        return
    order.delivery_boy_reference_id = partner_id
    if kind != "subscription":
        for line in checkout.siblings(db, order, statuses=EXTRA_UNPICKED_STATUSES):
            line.delivery_boy_reference_id = partner_id
    notify.delivery_partner(
        db, partner_id, "order_assigned", "New delivery assigned",
        f"{order.meal_slot.title()} delivery on {on}.",
        {"order_id": str(order.order_id if kind == "subscription" else order.extra_order_id), "kind": kind},
    )


# ── Changing a kitchen's partner ──────────────────────────────

def _end(row: DeliveryPartnerVendor, *, reason: str, actor_id, actor_type: str) -> None:
    row.status = "ended"
    row.ended_at = now_utc()
    row.ended_by = actor_id
    row.ended_by_type = actor_type
    row.end_reason = reason


def _row_view(row: DeliveryPartnerVendor) -> dict:
    return {
        "assignment_id": str(row.assignment_id),
        "delivery_boy_id": str(row.delivery_boy_reference_id),
        "provider_id": str(row.provider_reference_id),
        "status": row.status,
        "assigned_at": row.assigned_at.isoformat() if row.assigned_at else None,
        "end_reason": row.end_reason,
    }


def _take_over_work(db: Session, provider_id, boy: DeliveryBoy, previous_id, *, actor_id, actor_type: str) -> dict:
    """
    Give the kitchen's open work to `boy`: subscriptions with no partner or
    with the previous kitchen partner (other partners chosen by hand keep
    theirs), and one-time orders not picked up yet, from today on.
    """
    today = today_local()
    holders = [None] + ([previous_id] if previous_id else [])
    subs = (
        db.query(Subscription)
        .filter(
            Subscription.vendor_reference_id == provider_id,
            Subscription.status.in_(delivery_assignment.ASSIGNABLE_SUBSCRIPTION_STATUSES),
        )
        .order_by(Subscription.start_date.asc())
        .with_for_update()
        .all()
    )
    summary = {"subscriptions": 0, "meals": 0, "one_time_orders": 0, "kept_in_hand": 0}
    for sub in subs:
        holder = sub.delivery_boy_reference_id
        if holder is not None and str(holder) not in {str(h) for h in holders if h} \
                and delivery_assignment.inherited_partner(db, sub) is not None:
            continue  # assigned by hand to another partner who can still serve it
        result = delivery_assignment.assign(
            db, sub, boy, actor_id=actor_id, actor_type=actor_type,
            note="Kitchen's delivery partner", notify_parties=False,
        )
        if result["action"] != "unchanged" or result["newly_assigned"] or result["reassigned_from_other_partner"]:
            summary["subscriptions"] += 1
        summary["meals"] += result["newly_assigned"] + result["reassigned_from_other_partner"]
        summary["kept_in_hand"] += result["skipped"]["in_progress"]

    orders = (
        db.query(ExtraOrder)
        .filter(
            ExtraOrder.vendor_reference_id == provider_id,
            ExtraOrder.delivery_date >= today,
            ExtraOrder.status.in_(EXTRA_UNPICKED_STATUSES),
        )
        .with_for_update()
        .all()
    )
    off_days = partner_leave.leave_dates(
        db, boy.delivery_boy_id, today, max((o.delivery_date for o in orders), default=today)
    )
    for order in orders:
        holder = order.delivery_boy_reference_id
        if holder is not None and (previous_id is None or str(holder) != str(previous_id)):
            continue
        if str(holder) == str(boy.delivery_boy_id) or order.delivery_date in off_days:
            continue
        order.delivery_boy_reference_id = boy.delivery_boy_id
        summary["one_time_orders"] += 1
    if previous_id:
        summary["kept_in_hand"] += db.query(ExtraOrder).filter(
            ExtraOrder.vendor_reference_id == provider_id,
            ExtraOrder.delivery_boy_reference_id == previous_id,
            ExtraOrder.status.in_(IN_HAND_STATUSES),
        ).count()
    return summary


def _release_outside(db: Session, boy: DeliveryBoy, keep: set[str], *, actor_id, actor_type: str) -> int:
    """A pool partner who now serves set kitchens drops work of every other kitchen."""
    released = 0
    subs = db.query(Subscription).filter(Subscription.delivery_boy_reference_id == boy.delivery_boy_id).all()
    for provider_id in {str(s.vendor_reference_id) for s in subs} - keep:
        released += delivery_assignment.release_partner_subscriptions(
            db, boy.delivery_boy_id, reason="partner_moved_kitchen", actor_id=actor_id, actor_type=actor_type,
            only_provider_id=provider_id,
        )
    released += _release_orders(db, boy.delivery_boy_id, exclude_provider_ids=keep)
    return released


def _release_orders(db: Session, delivery_boy_id, *, provider_id=None, exclude_provider_ids=None) -> int:
    """Unassign the partner's one-time orders and loose meals that are not picked up yet."""
    n = 0
    today = today_local()
    for model, day_col, statuses in (
        (Order, Order.order_date, SUB_UNPICKED_STATUSES),
        (ExtraOrder, ExtraOrder.delivery_date, EXTRA_UNPICKED_STATUSES),
    ):
        q = db.query(model).filter(
            model.delivery_boy_reference_id == delivery_boy_id,
            model.status.in_(statuses),
            day_col >= today,
        )
        if provider_id is not None:
            q = q.filter(model.vendor_reference_id == provider_id)
        if exclude_provider_ids:
            q = q.filter(model.vendor_reference_id.notin_(list(exclude_provider_ids)))
        n += q.update({model.delivery_boy_reference_id: None}, synchronize_session=False)
    return n


def assign_kitchen(db: Session, boy: DeliveryBoy, provider: Provider, *, actor_id, actor_type: str = "admin",
                   note: str | None = None, ip: str | None = None) -> dict:
    """
    Make `boy` the current partner of `provider` (adding it to the partner's
    kitchens; their other kitchens are kept). Moves the kitchen from its
    previous partner when it had one. Assigning the same pair again only
    picks up work still missing a partner.
    """
    if not usable(boy):
        raise DomainError(
            "Only active, approved delivery partners can be given kitchens.", 409, code="PARTNER_NOT_ELIGIBLE",
        )
    current = kitchen_row(db, provider.provider_id, lock=True)
    partner_kitchens = {str(r.provider_reference_id) for r in partner_rows(db, boy.delivery_boy_id, lock=True)}
    was_pool = not partner_kitchens

    previous_id = None
    if current is not None and str(current.delivery_boy_reference_id) == str(boy.delivery_boy_id):
        row, action = current, "unchanged"
    else:
        if current is not None:
            previous_id = current.delivery_boy_reference_id
            _end(current, reason="moved_to_other_partner", actor_id=actor_id, actor_type=actor_type)
            db.flush()
        row = DeliveryPartnerVendor(
            delivery_boy_reference_id=boy.delivery_boy_id,
            provider_reference_id=provider.provider_id,
            status="active",
            assigned_by=actor_id,
            assigned_by_type=actor_type,
            note=note,
        )
        db.add(row)
        db.flush()
        action = "moved" if previous_id else "assigned"

    released = 0
    if was_pool:
        released = _release_outside(db, boy, {str(provider.provider_id)}, actor_id=actor_id, actor_type=actor_type)
    work = _take_over_work(db, provider.provider_id, boy, previous_id, actor_id=actor_id, actor_type=actor_type)

    total_kitchens = len(partner_kitchens | {str(provider.provider_id)})
    if action != "unchanged" or work["subscriptions"] or work["one_time_orders"]:
        notify.delivery_partner(
            db, boy.delivery_boy_id, "vendor_assigned", "Kitchen assigned to you",
            f"You now deliver for {provider.business_name or 'a kitchen'} ({kitchen_address(provider) or 'see the app'}). "
            f"{work['subscriptions']} subscription(s) and {work['one_time_orders']} one-time order(s) are yours.",
            {"provider_id": str(provider.provider_id), "kind": "vendor_assignment"},
        )
    if action != "unchanged":
        notify.kitchen(
            db, provider.provider_id, "partner_assigned",
            "Delivery partner changed" if previous_id else "Delivery partner assigned",
            f"{boy.full_name or 'A delivery partner'} now collects your orders and subscription meals.",
            {"delivery_boy_id": str(boy.delivery_boy_id)},
        )
    if previous_id:
        notify.delivery_partner(
            db, previous_id, "vendor_unassigned", "Kitchen moved to another partner",
            f"{provider.business_name or 'A kitchen'} is no longer yours. Orders you have already picked up stay with you.",
            {"provider_id": str(provider.provider_id), "kind": "vendor_assignment"},
        )
    summary = {
        "action": action,
        "delivery_boy_id": str(boy.delivery_boy_id),
        "provider_id": str(provider.provider_id),
        "previous_delivery_boy_id": str(previous_id) if previous_id else None,
        "assigned_vendor_count": total_kitchens,
        "subscriptions_assigned": work["subscriptions"],
        "meals_assigned": work["meals"],
        "one_time_orders_assigned": work["one_time_orders"],
        "kept_with_previous_partner": work["kept_in_hand"],
        "released_from_other_kitchens": released,
    }
    record_audit(
        db, table="delivery.delivery_partner_vendors", record_id=row.assignment_id,
        operation="I" if action != "unchanged" else "U",
        old={"delivery_boy_id": previous_id} if previous_id else None,
        new={"event": f"kitchen_{action}", "note": note, **summary},
        actor_id=actor_id, actor_type=actor_type, ip=ip,
    )
    business_event("kitchen.partner_assigned", **{k: summary[k] for k in ("action", "delivery_boy_id", "provider_id")})
    return summary


def remove_kitchen(db: Session, boy: DeliveryBoy, provider_id, *, actor_id, actor_type: str = "admin",
                   reason: str | None = None, ip: str | None = None) -> dict:
    """Take one kitchen away from a partner; their other kitchens are not touched."""
    row = (
        db.query(DeliveryPartnerVendor)
        .filter(
            DeliveryPartnerVendor.provider_reference_id == provider_id,
            DeliveryPartnerVendor.delivery_boy_reference_id == boy.delivery_boy_id,
            DeliveryPartnerVendor.status == "active",
        )
        .with_for_update()
        .first()
    )
    if row is None:
        raise DomainError("This kitchen is not assigned to the delivery partner", 404)
    _end(row, reason="removed", actor_id=actor_id, actor_type=actor_type)
    db.flush()

    subs = delivery_assignment.release_partner_subscriptions(
        db, boy.delivery_boy_id, reason="kitchen_removed_from_partner", actor_id=actor_id, actor_type=actor_type,
        only_provider_id=provider_id,
    )
    orders = _release_orders(db, boy.delivery_boy_id, provider_id=provider_id)
    provider = db.query(Provider).filter(Provider.provider_id == provider_id).first()
    name = (provider.business_name if provider else None) or "A kitchen"
    notify.delivery_partner(
        db, boy.delivery_boy_id, "vendor_unassigned", "Kitchen removed",
        f"{name} is no longer assigned to you. Orders you have already picked up stay with you.",
        {"provider_id": str(provider_id), "kind": "vendor_assignment"},
    )
    notify.kitchen(
        db, provider_id, "partner_unassigned", "Delivery partner removed",
        "Your kitchen has no delivery partner right now. Orleeno will assign one; new orders wait for them.",
        {"delivery_boy_id": str(boy.delivery_boy_id)},
    )
    remaining = len(vendor_ids(db, boy.delivery_boy_id))
    summary = {
        "delivery_boy_id": str(boy.delivery_boy_id),
        "provider_id": str(provider_id),
        "subscriptions_unassigned": subs,
        "orders_unassigned": orders,
        "assigned_vendor_count": remaining,
    }
    record_audit(
        db, table="delivery.delivery_partner_vendors", record_id=row.assignment_id,
        old=_row_view(row) | {"status": "active"}, new={"event": "kitchen_removed", "reason": reason, **summary},
        actor_id=actor_id, actor_type=actor_type, ip=ip,
    )
    business_event("kitchen.partner_removed", delivery_boy_id=boy.delivery_boy_id, provider_id=provider_id)
    return summary


def open_task_counts(db: Session, delivery_boy_id, provider_ids) -> dict:
    """{provider_id: open tasks of this partner from today on} for a list of kitchens."""
    ids = list({p for p in provider_ids if p is not None})
    if not ids:
        return {}
    today = today_local()
    counts: dict = {pid: 0 for pid in ids}
    for model, day_col, statuses in (
        (Order, Order.order_date, SUB_UNPICKED_STATUSES + IN_HAND_STATUSES),
        (ExtraOrder, ExtraOrder.delivery_date, EXTRA_UNPICKED_STATUSES + IN_HAND_STATUSES),
    ):
        for pid, n in (
            db.query(model.vendor_reference_id, func.count())
            .filter(
                model.delivery_boy_reference_id == delivery_boy_id,
                model.vendor_reference_id.in_(ids),
                model.status.in_(statuses),
                day_col >= today,
            )
            .group_by(model.vendor_reference_id)
        ):
            counts[pid] = counts.get(pid, 0) + n
    return counts
