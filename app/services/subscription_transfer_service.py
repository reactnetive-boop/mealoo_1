"""
Moving a kitchen's running subscriptions to another kitchen (BE-B8).

Used when a kitchen closes or stops serving an area. A subscription can move
when the target kitchen sells the same package (a catalogue package it
offers), is open, approved and delivers to the customer's pincode, and has
room for the remaining meals. The customer keeps the price they paid and the
new kitchen earns the same per meal (the pricing snapshot does not change);
nothing is charged or refunded. Meals already with a partner or delivered
stay as they are.

Subscriptions that cannot move (the old kitchen's own packages, or no room)
are listed; with cancel_untransferable they are cancelled and every unused
meal is refunded, so the old kitchen can then be deactivated.
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.audit import business_event, record_audit
from app.core.clock import today_local
from app.core.errors import DomainError
from app.domain import capacity, notify
from app.domain.delivery_assignment import partner_block_reason, unassign
from app.domain.eligibility import kitchen_serves, offering, parse_pincode, provider_block_reason
from app.domain.slots import expand_plan_slot
from app.domain.status import SUB_UNPICKED_STATUSES
from app.models.delivery_boy_model import DeliveryBoy
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.user_address_model import UserAddress


def _blocker(db: Session, sub: Subscription, package: SubscriptionPackage | None, target: Provider) -> str | None:
    if package is None:
        return "subscription has no package"
    if offering(db, target.provider_id, package.package_reference_id) is None:
        return "the target kitchen does not sell this package"
    address = db.query(UserAddress).filter(UserAddress.user_address_id == sub.user_address_reference_id).first()
    if address is None or not kitchen_serves(db, target, parse_pincode(address.pin_code)):
        return "the target kitchen does not deliver to the customer's pincode"
    if sub.status == "active":
        try:
            capacity.assert_room(
                db, provider_id=target.provider_id, package_id=package.package_reference_id,
                package_name="this package", slots=expand_plan_slot(sub.meal_slot),
                start=max(today_local(), sub.start_date), end=sub.end_date - timedelta(days=1),
                quantity=package.quantity,
            )
        except DomainError as exc:
            return exc.message
    return None


def _move(db: Session, sub: Subscription, source: Provider, target: Provider, admin_id: str, reason: str,
          ip: str | None) -> None:
    if sub.delivery_boy_reference_id:
        boy = db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == sub.delivery_boy_reference_id).first()
        if partner_block_reason(boy, target.provider_id):
            unassign(db, sub, actor_id=admin_id, actor_type="admin", note="subscription moved to another kitchen", ip=ip)
    sub.vendor_reference_id = target.provider_id
    moved_meals = db.query(Order).filter(
        Order.subscription_reference_id == sub.subscription_id,
        Order.order_date >= today_local(),
        Order.status.in_(SUB_UNPICKED_STATUSES),
    ).with_for_update().all()
    for meal in moved_meals:
        meal.vendor_reference_id = target.provider_id
        meal.pickup_code_attempts = 0
        meal.status = "scheduled"  # the new kitchen starts it from scratch
    # a paused plan's future meals come back on resume: at the new kitchen
    db.query(Order).filter(
        Order.subscription_reference_id == sub.subscription_id,
        Order.order_date >= today_local(),
        Order.status == "cancelled",
        Order.cancel_reason == "paused",
    ).update({"vendor_reference_id": target.provider_id}, synchronize_session=False)
    record_audit(
        db, table="subscription.subscriptions", record_id=sub.subscription_id,
        old={"vendor_id": source.provider_id},
        new={"vendor_id": target.provider_id, "event": "subscription_transferred", "reason": reason},
        actor_id=admin_id, actor_type="admin", ip=ip,
    )
    notify.customer(
        db, sub.user_reference_id, "subscription_update", "Your meals are coming from a new kitchen",
        f"{target.business_name} now prepares your subscription meals. Your plan and price stay the same.",
        {"subscription_id": str(sub.subscription_id)},
    )
    notify.kitchen(
        db, target.provider_id, "new_subscription", "Subscription moved to you",
        f"Orleeno moved a running subscription to your kitchen: {len(moved_meals)} upcoming meal(s).",
        {"subscription_id": str(sub.subscription_id)},
    )


class SubscriptionTransferService:

    @staticmethod
    def transfer(db: Session, source_id, payload, admin_id: str, ip: str | None = None) -> dict:
        if str(source_id) == str(payload.target_provider_id):
            raise DomainError("Choose a different kitchen to move the subscriptions to")
        source = db.query(Provider).filter(Provider.provider_id == source_id).first()
        if source is None:
            raise DomainError("Provider not found", 404)
        # lock the target kitchen: capacity checks below must not race new orders
        target = db.query(Provider).filter(Provider.provider_id == payload.target_provider_id).with_for_update().first()
        reason = provider_block_reason(target)
        if reason:
            raise DomainError(f"Target kitchen cannot take subscriptions: {reason}")

        q = db.query(Subscription).filter(
            Subscription.vendor_reference_id == source.provider_id,
            Subscription.status.in_(("active", "paused")),
        )
        if payload.subscription_ids:
            q = q.filter(Subscription.subscription_id.in_(payload.subscription_ids))
        subs = q.with_for_update().all()

        movable, blocked = [], []
        for sub in subs:
            package = db.query(SubscriptionPackage).filter(
                SubscriptionPackage.subscription_reference_id == sub.subscription_id
            ).first()
            why = _blocker(db, sub, package, target)
            if why:
                blocked.append((sub, why))
                continue
            movable.append(sub)
            if not payload.preview:
                # moved right away, so the next capacity check counts these meals
                _move(db, sub, source, target, admin_id, payload.reason, ip)
                db.flush()

        result = {
            "success": True,
            "preview": payload.preview,
            "target_provider_id": target.provider_id,
            "movable": [str(s.subscription_id) for s in movable],
            "blocked": [{"subscription_id": str(s.subscription_id), "reason": why} for s, why in blocked],
            "cancelled": [],
        }
        if payload.preview:
            return result

        if payload.cancel_untransferable and blocked:
            from app.services.subscription_service import SubscriptionService

            for sub, why in blocked:
                outcome = SubscriptionService.cancel(
                    db, sub, reason=f"Kitchen closed - {payload.reason}", actor="admin",
                )
                result["cancelled"].append({"subscription_id": str(sub.subscription_id), **outcome})

        if movable or result["cancelled"]:
            notify.kitchen(
                db, source.provider_id, "subscription_update", "Subscriptions moved",
                f"Orleeno moved {len(movable)} subscription(s) to another kitchen"
                + (f" and cancelled {len(result['cancelled'])}" if result["cancelled"] else "") + ".",
            )
        db.commit()
        business_event("subscriptions.transferred", source=source.provider_id, target=target.provider_id,
                       moved=len(movable), cancelled=len(result["cancelled"]), admin_id=admin_id)
        return result
