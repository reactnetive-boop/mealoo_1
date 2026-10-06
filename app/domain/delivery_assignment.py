"""
Subscription-level delivery partner assignment.

An admin assigns one partner to a whole subscription instead of to every
meal. The subscription keeps a pointer to its current partner
(subscriptions.delivery_boy_reference_id) and every change is a row in
subscription_delivery_assignments, so history is never overwritten.

What an assignment touches (all inside the caller's transaction, with the
subscription and its meals row-locked):

  meals from today on, still at the kitchen   -> given to the new partner
  (scheduled / preparing / ready_for_pickup)
  meals already picked up / out for delivery  -> stay with whoever carries them
  delivered / skipped / cancelled meals       -> untouched (history)
  earlier days                                -> untouched

Meals generated later (midnight job, resume, renewal of the period) inherit
the subscription's partner. Meals cancelled by a pause are not assigned; they
pick up the current partner if the subscription is resumed.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import record_audit, business_event
from app.core.clock import now_utc, today_local
from app.core.errors import DomainError
from app.domain import notify, partner_leave
from app.domain.status import SUB_UNPICKED_STATUSES, IN_HAND_STATUSES
from app.models.delivery_boy_model import DeliveryBoy
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.subscription_delivery_assignment_model import SubscriptionDeliveryAssignment
from app.models.subscription_model import Subscription
from app.models.user_model import User

ASSIGNABLE_SUBSCRIPTION_STATUSES = ("active", "paused")


def partner_block_reason(boy: DeliveryBoy | None, provider_id) -> str | None:
    """Why this partner cannot serve this kitchen's subscriptions (None = can)."""
    if boy is None:
        return "not found"
    if not boy.is_active:
        return "deactivated"
    if boy.approval_status != "approved":
        return "not approved yet"
    if boy.assigned_provider_reference_id is not None and str(boy.assigned_provider_reference_id) != str(provider_id):
        return "dedicated to another kitchen"
    return None


def inherited_partner(db: Session, sub: Subscription):
    """Partner new meals of `sub` should get, or None if it has none / can no longer serve."""
    if not sub.delivery_boy_reference_id:
        return None
    boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == sub.delivery_boy_reference_id).first()
    if partner_block_reason(boy, sub.vendor_reference_id):
        return None
    return boy.delivery_boy_id


def active_assignment(db: Session, subscription_id, lock: bool = False) -> SubscriptionDeliveryAssignment | None:
    q = db.query(SubscriptionDeliveryAssignment).filter(
        SubscriptionDeliveryAssignment.subscription_reference_id == subscription_id,
        SubscriptionDeliveryAssignment.status == "active",
    )
    if lock:
        q = q.with_for_update()
    return q.first()


def _end(row: SubscriptionDeliveryAssignment | None, *, reason: str, actor_id, actor_type: str) -> None:
    if row is None:
        return
    row.status = "ended"
    row.ended_at = now_utc()
    row.ended_by = actor_id
    row.ended_by_type = actor_type
    row.end_reason = reason


def _start(db: Session, sub: Subscription, boy_id, *, actor_id, actor_type: str, note: str | None) -> SubscriptionDeliveryAssignment:
    row = SubscriptionDeliveryAssignment(
        subscription_reference_id=sub.subscription_id,
        delivery_boy_reference_id=boy_id,
        status="active",
        assigned_by=actor_id,
        assigned_by_type=actor_type,
        note=note,
    )
    db.add(row)
    db.flush()
    return row


def _labels(db: Session, sub: Subscription) -> tuple[str, str]:
    user = db.query(User).filter(User.user_id == sub.user_reference_id).first()
    provider = db.query(Provider).filter(Provider.provider_id == sub.vendor_reference_id).first()
    customer = (user.full_name or "").split()[0] if user and user.full_name else "A customer"
    kitchen = (provider.business_name if provider else None) or "the kitchen"
    return customer, kitchen


def assign(
    db: Session,
    sub: Subscription,
    boy: DeliveryBoy,
    *,
    actor_id,
    actor_type: str = "admin",
    note: str | None = None,
    ip: str | None = None,
) -> dict:
    """
    Give `sub` and its open meals to `boy`. `sub` must already be row-locked.

    Safe to repeat: assigning the partner a subscription already has only
    picks up open meals that are still missing a partner.
    """

    if sub.status not in ASSIGNABLE_SUBSCRIPTION_STATUSES:
        raise DomainError(
            f"Only active or paused subscriptions can be assigned (this one is {sub.status}).",
            409,
            code="SUBSCRIPTION_NOT_ASSIGNABLE",
        )
    reason = partner_block_reason(boy, sub.vendor_reference_id)
    if reason:
        raise DomainError(f"This delivery partner cannot take this subscription: {reason}.", code="PARTNER_NOT_ELIGIBLE")

    previous_id = sub.delivery_boy_reference_id
    same_partner = previous_id is not None and str(previous_id) == str(boy.delivery_boy_id)
    current = active_assignment(db, sub.subscription_id, lock=True)
    if same_partner and current is not None:
        row = current
        action = "unchanged"
    else:
        _end(current, reason="reassigned", actor_id=actor_id, actor_type=actor_type)
        db.flush()
        row = _start(db, sub, boy.delivery_boy_id, actor_id=actor_id, actor_type=actor_type, note=note)
        action = "reassigned" if previous_id else "assigned"
    sub.delivery_boy_reference_id = boy.delivery_boy_id

    today = today_local()
    meals = (
        db.query(Order)
        .filter(Order.subscription_reference_id == sub.subscription_id, Order.order_date >= today)
        .order_by(Order.order_date.asc(), Order.meal_slot.asc())
        .with_for_update()
        .all()
    )
    newly = moved = already = 0
    skipped = {"in_progress": 0, "delivered": 0, "skipped": 0, "cancelled": 0, "past": 0, "partner_on_leave": 0}
    others_notified: set[str] = set()
    off_days = partner_leave.leave_dates(
        db, boy.delivery_boy_id, today, max((m.order_date for m in meals), default=today)
    )
    for meal in meals:
        if meal.status in SUB_UNPICKED_STATUSES and meal.order_date in off_days:
            skipped["partner_on_leave"] += 1  # stays with whoever has it (or nobody) that day
            continue
        if meal.status in SUB_UNPICKED_STATUSES:
            holder = meal.delivery_boy_reference_id
            if holder is None:
                newly += 1
            elif str(holder) == str(boy.delivery_boy_id):
                already += 1
            else:
                moved += 1
                if previous_id is None or str(holder) != str(previous_id):
                    others_notified.add(str(holder))
            meal.delivery_boy_reference_id = boy.delivery_boy_id
        elif meal.status in IN_HAND_STATUSES:
            skipped["in_progress"] += 1
        elif meal.status in skipped:
            skipped[meal.status] += 1

    past_total = 0
    for status, count in (
        db.query(Order.status, func.count())
        .filter(Order.subscription_reference_id == sub.subscription_id, Order.order_date < today)
        .group_by(Order.status)
    ):
        past_total += count
        if status in ("delivered", "skipped", "cancelled"):
            skipped[status] += count
        else:
            skipped["past"] += count

    assigned_total = newly + moved + already
    if action != "unchanged":
        row.orders_assigned = assigned_total

    customer, kitchen = _labels(db, sub)
    if action != "unchanged" or newly or moved:
        notify.delivery_partner(
            db, boy.delivery_boy_id, "subscription_assigned", "New subscription assigned",
            f"{customer}'s {sub.meal_slot.replace('_', ' ')} subscription from {kitchen}: "
            f"{assigned_total} upcoming deliveries are now yours.",
            {"subscription_id": str(sub.subscription_id), "kind": "subscription_assignment"},
        )
    if action != "unchanged":
        notify.kitchen(
            db, sub.vendor_reference_id, "partner_assigned",
            "Delivery partner changed" if action == "reassigned" else "Delivery partner assigned",
            f"{boy.full_name or 'A delivery partner'} will deliver {customer}'s {sub.meal_slot.replace('_', ' ')} "
            f"subscription ({assigned_total} upcoming meals).",
            {"subscription_id": str(sub.subscription_id)},
        )
    if previous_id and not same_partner:
        notify.delivery_partner(
            db, previous_id, "subscription_unassigned", "Subscription reassigned",
            f"{customer}'s subscription from {kitchen} moved to another partner. "
            "Meals you have already picked up stay with you.",
            {"subscription_id": str(sub.subscription_id), "kind": "subscription_assignment"},
        )
    for other in others_notified:
        notify.delivery_partner(
            db, other, "schedule_update", "Deliveries reassigned",
            f"Upcoming deliveries for {customer}'s subscription were moved to another partner.",
            {"subscription_id": str(sub.subscription_id), "kind": "subscription_assignment"},
        )

    summary = {
        "subscription_id": str(sub.subscription_id),
        "delivery_boy_id": str(boy.delivery_boy_id),
        "delivery_boy_name": boy.full_name,
        "previous_delivery_boy_id": str(previous_id) if previous_id else None,
        "action": action,
        "assigned_orders": assigned_total,
        "newly_assigned": newly,
        "reassigned_from_other_partner": moved,
        "already_assigned": already,
        "skipped": skipped,
        "total_orders": len(meals) + past_total,
        "partner_online": bool(boy.is_online),
    }
    record_audit(
        db, table="subscription.subscriptions", record_id=sub.subscription_id,
        old={"delivery_boy_id": previous_id},
        new={"event": f"subscription_delivery_{action}", "note": note, **summary},
        actor_id=actor_id, actor_type=actor_type, ip=ip,
    )
    business_event(
        "subscription.delivery_assigned", subscription_id=sub.subscription_id, delivery_boy_id=boy.delivery_boy_id,
        action=action, orders=assigned_total, by=actor_type,
    )
    return summary


def _release_meals(db: Session, sub: Subscription, delivery_boy_id) -> int:
    meals = (
        db.query(Order)
        .filter(
            Order.subscription_reference_id == sub.subscription_id,
            Order.order_date >= today_local(),
            Order.status.in_(SUB_UNPICKED_STATUSES),
            Order.delivery_boy_reference_id == delivery_boy_id,
        )
        .with_for_update()
        .all()
    )
    for meal in meals:
        meal.delivery_boy_reference_id = None
    return len(meals)


def unassign(db: Session, sub: Subscription, *, actor_id, actor_type: str = "admin", note: str | None = None, ip: str | None = None) -> dict:
    """Remove the subscription's partner; open meals go back to 'unassigned'."""

    previous_id = sub.delivery_boy_reference_id
    if previous_id is None:
        raise DomainError("No delivery partner is assigned to this subscription.", 409, code="NOT_ASSIGNED")
    _end(active_assignment(db, sub.subscription_id, lock=True), reason="unassigned", actor_id=actor_id, actor_type=actor_type)
    sub.delivery_boy_reference_id = None
    released = _release_meals(db, sub, previous_id)

    customer, kitchen = _labels(db, sub)
    notify.kitchen(
        db, sub.vendor_reference_id, "partner_unassigned", "Delivery partner removed",
        f"{customer}'s {sub.meal_slot.replace('_', ' ')} subscription has no delivery partner for now; "
        f"{released} upcoming meal(s) are unassigned. Orleeno will assign someone.",
        {"subscription_id": str(sub.subscription_id)},
    )
    notify.delivery_partner(
        db, previous_id, "subscription_unassigned", "Subscription removed",
        f"{customer}'s subscription from {kitchen} is no longer assigned to you. "
        "Meals you have already picked up stay with you.",
        {"subscription_id": str(sub.subscription_id), "kind": "subscription_assignment"},
    )
    record_audit(
        db, table="subscription.subscriptions", record_id=sub.subscription_id,
        old={"delivery_boy_id": previous_id},
        new={"event": "subscription_delivery_unassigned", "released_orders": released, "note": note},
        actor_id=actor_id, actor_type=actor_type, ip=ip,
    )
    return {
        "subscription_id": str(sub.subscription_id),
        "previous_delivery_boy_id": str(previous_id),
        "released_orders": released,
    }


def release_partner_subscriptions(db: Session, delivery_boy_id, *, reason: str, actor_id, actor_type: str, keep_provider_id=None) -> int:
    """
    End this partner's subscription assignments (all of them, or those of
    kitchens other than `keep_provider_id`) and free their open meals.
    Used when a partner is deactivated, rejected or dedicated to one kitchen.
    """

    q = db.query(Subscription).filter(Subscription.delivery_boy_reference_id == delivery_boy_id)
    if keep_provider_id is not None:
        q = q.filter(Subscription.vendor_reference_id != keep_provider_id)
    subs = q.with_for_update().all()
    for sub in subs:
        _end(active_assignment(db, sub.subscription_id, lock=True), reason=reason, actor_id=actor_id, actor_type=actor_type)
        sub.delivery_boy_reference_id = None
        released = _release_meals(db, sub, delivery_boy_id)
        notify.kitchen(
            db, sub.vendor_reference_id, "partner_unassigned", "Delivery partner removed",
            f"The partner for one of your subscriptions is no longer available; {released} upcoming meal(s) "
            "are unassigned. Orleeno will assign someone.",
            {"subscription_id": str(sub.subscription_id)},
        )
        record_audit(
            db, table="subscription.subscriptions", record_id=sub.subscription_id,
            old={"delivery_boy_id": delivery_boy_id},
            new={"event": "subscription_delivery_unassigned", "reason": reason},
            actor_id=actor_id, actor_type=actor_type,
        )
    return len(subs)


def carry_over(db: Session, old_sub: Subscription, new_sub: Subscription) -> None:
    """On a package switch the new subscription keeps the partner if they can serve its kitchen."""

    boy_id = old_sub.delivery_boy_reference_id
    if boy_id is None:
        return
    _end(active_assignment(db, old_sub.subscription_id, lock=True), reason="subscription_switched", actor_id=None, actor_type="system")
    old_sub.delivery_boy_reference_id = None
    boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == boy_id).first()
    if partner_block_reason(boy, new_sub.vendor_reference_id):
        return
    new_sub.delivery_boy_reference_id = boy_id
    _start(
        db, new_sub, boy_id, actor_id=None, actor_type="system",
        note=f"Carried over from switched subscription {old_sub.subscription_id}",
    )
