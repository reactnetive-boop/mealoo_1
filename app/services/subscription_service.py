"""
Customer subscriptions.

Lifecycle:  active -> paused -> active          (pause / resume)
            active|paused -> cancelled           (customer or admin)
            active -> switched                   (package switch)
            active -> expired                    (midnight job after end_date)

end_date is exclusive: meals are served on start_date .. end_date - 1.

Money: the full plan price (pricing engine, frozen in pricing_snapshot) is
debited from the wallet up front. Free skips and cancellations return the
value of each cancelled meal (snapshot per-meal price) to the wallet, once
per meal.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import business_event
from app.core.clock import now_utc, today_local
from app.core.config import (
    SUBSCRIPTION_MAX_START_DAYS_AHEAD,
    CUSTOM_PLAN_MIN_DAYS,
    CUSTOM_PLAN_MAX_DAYS,
)
from app.core.errors import DomainError
from app.domain import capacity, ledger, notify, orders as meals
from app.domain.eligibility import assert_sellable
from app.domain.pricing import (
    build_quote,
    current_components,
    quote_view,
    subscription_unit_price,
    money,
    ZERO,
)
from app.domain.slots import (
    expand_plan_slot,
    package_serves,
    earliest_service_date,
    is_before_cutoff,
    SLOT_CUTOFFS,
    cutoff_at,
)
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.subscription_plan_model import SubscriptionPlan
from app.models.user_address_model import UserAddress
from app.repositories.cart_repository import CartRepository
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.repositories.subscription_repository import SubscriptionRepository

# Kept for importers (switch service, admin)
MEAL_SLOT_EXPANSION = {
    k: expand_plan_slot(k)
    for k in ("breakfast", "lunch", "dinner", "breakfast_lunch", "lunch_dinner", "breakfast_dinner", "all_slots")
}
MEAL_SLOT_MULTIPLIER = {k: len(v) for k, v in MEAL_SLOT_EXPANSION.items()}


def is_custom_plan(plan: SubscriptionPlan) -> bool:
    return plan.subscription_type == "custom" or (plan.duration_days or 0) <= 0


def owned_address(db: Session, user_id: str, address_id) -> UserAddress:
    address = (
        db.query(UserAddress)
        .filter(
            UserAddress.user_address_id == address_id,
            UserAddress.user_reference_id == user_id,
            UserAddress.is_active == True,  # noqa: E712
        )
        .first()
    )
    if address is None:
        raise DomainError("Invalid delivery address")
    return address


def owned_subscription(db: Session, user_id: str, subscription_id, lock: bool = False) -> Subscription:
    q = db.query(Subscription).filter(
        Subscription.subscription_id == subscription_id,
        Subscription.user_reference_id == user_id,
    )
    if lock:
        q = q.with_for_update()
    subscription = q.first()
    if subscription is None:
        # Same answer for "not yours" and "does not exist": no ID probing
        raise HTTPException(status_code=404, detail="Subscription not found")
    return subscription


def resolve_term(plan: SubscriptionPlan, start_date: date, end_date: date | None) -> tuple[date, int]:
    """(exclusive end date, number of days) for a plan starting on start_date."""

    if is_custom_plan(plan):
        if end_date is None:
            raise DomainError("Choose an end date for a custom plan")
        days = (end_date - start_date).days + 1
        if days < CUSTOM_PLAN_MIN_DAYS or days > CUSTOM_PLAN_MAX_DAYS:
            raise DomainError(
                f"A custom plan must be between {CUSTOM_PLAN_MIN_DAYS} and {CUSTOM_PLAN_MAX_DAYS} days"
            )
    else:
        days = int(plan.duration_days)
    return start_date + timedelta(days=days), days


def validate_start(slots: list[str], start_date: date) -> None:
    earliest = earliest_service_date(slots)
    if start_date < earliest:
        raise DomainError(
            f"The earliest start date for this meal plan is {earliest} "
            f"(same-day cut-offs: " + ", ".join(f"{s} {SLOT_CUTOFFS[s].strftime('%H:%M')}" for s in slots) + ")",
            code="START_DATE_TOO_EARLY",
        )
    if start_date > today_local() + timedelta(days=SUBSCRIPTION_MAX_START_DAYS_AHEAD):
        raise DomainError(f"A subscription can start at most {SUBSCRIPTION_MAX_START_DAYS_AHEAD} days ahead")


def subscription_view(db: Session, sub: Subscription) -> dict:
    package_row = (
        db.query(SubscriptionPackage, MenuPackage)
        .join(MenuPackage, MenuPackage.package_id == SubscriptionPackage.package_reference_id)
        .filter(SubscriptionPackage.subscription_reference_id == sub.subscription_id)
        .first()
    )
    provider = db.query(Provider).filter(Provider.provider_id == sub.vendor_reference_id).first()
    address = db.query(UserAddress).filter(UserAddress.user_address_id == sub.user_address_reference_id).first()
    today = today_local()
    next_meal = (
        db.query(Order)
        .filter(
            Order.subscription_reference_id == sub.subscription_id,
            Order.order_date >= today,
            Order.status.in_(("scheduled", "preparing", "out_for_delivery")),
        )
        .order_by(Order.order_date.asc(), Order.meal_slot.asc())
        .first()
    )
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.subscription_plan_id == sub.plan_reference_id).first()

    return {
        "subscription_id": sub.subscription_id,
        "user_reference_id": sub.user_reference_id,
        "vendor_reference_id": sub.vendor_reference_id,
        "vendor_name": provider.business_name if provider else None,
        "plan_reference_id": sub.plan_reference_id,
        "plan_duration_days": plan.duration_days if plan else None,
        "user_address_reference_id": sub.user_address_reference_id,
        "address_line": ", ".join(p for p in (
            address.address_line1 if address else None,
            address.city if address else None,
            address.pin_code if address else None,
        ) if p),
        "status": sub.status,
        "meal_slot": sub.meal_slot,
        "subscription_type": sub.subscription_type,
        "start_date": sub.start_date,
        "end_date": sub.end_date,
        "last_meal_date": sub.end_date - timedelta(days=1),
        "free_skips_total": sub.free_skips_total or 0,
        "free_skips_used": sub.free_skips_used or 0,
        "total_amount": sub.total_amount,
        "discount_amount": sub.discount_amount,
        "charges_amount": sub.charges_amount,
        "final_amount": sub.final_amount,
        "refunded_amount": sub.refunded_amount,
        "pause_start_date": sub.pause_start_date,
        "total_days_paused": sub.total_days_paused or 0,
        "notes": sub.notes,
        "cancelled_at": sub.cancelled_at,
        "cancel_reason": sub.cancel_reason,
        "created_at": sub.created_at,
        "package_id": package_row[1].package_id if package_row else None,
        "package_name": package_row[1].package_name if package_row else None,
        "quantity": package_row[0].quantity if package_row else None,
        "unit_price": package_row[0].unit_price if package_row else None,
        "meal_value": meals.meal_value(sub),
        "price_breakdown": quote_view(sub.pricing_snapshot) if sub.pricing_snapshot else None,
        "next_meal": {
            "order_id": next_meal.order_id,
            "order_date": next_meal.order_date,
            "meal_slot": next_meal.meal_slot,
            "status": next_meal.status,
        } if next_meal else None,
        "can_pause": sub.status == "active" and (today + timedelta(days=1)) < sub.end_date,
        "can_resume": sub.status == "paused",
        "can_cancel": sub.status in ("active", "paused"),
        "can_switch": sub.status == "active",
        "packages": [
            {
                "subscription_package_id": sp.subscription_package_id,
                "package_reference_id": sp.package_reference_id,
                "quantity": sp.quantity,
                "unit_price": sp.unit_price,
            }
            for sp in sub.packages
        ],
    }


class SubscriptionService:

    @staticmethod
    def get_plan_options(db: Session):
        return {
            "meal_slots": SubscriptionPlanRepository.get_distinct_meal_slots(db),
            "subscription_types": SubscriptionPlanRepository.get_distinct_subscription_types(db),
        }

    @staticmethod
    def list_plans(db: Session, meal_slot: str = None, subscription_type: str = None):
        plans = SubscriptionPlanRepository.get_all_active(db, meal_slot=meal_slot, subscription_type=subscription_type)
        return {
            "success": True,
            "total": len(plans),
            "plans": [
                {
                    "subscription_plan_id": p.subscription_plan_id,
                    "subscription_type": p.subscription_type,
                    "meal_slot": p.meal_slot,
                    "meal_slots": expand_plan_slot(p.meal_slot),
                    "duration_days": p.duration_days,
                    "is_custom": is_custom_plan(p),
                    "custom_min_days": CUSTOM_PLAN_MIN_DAYS if is_custom_plan(p) else None,
                    "custom_max_days": CUSTOM_PLAN_MAX_DAYS if is_custom_plan(p) else None,
                    "free_skips": p.free_skips or 0,
                    "discount_percent": p.discount_percent,
                    "earliest_start_date": earliest_service_date(expand_plan_slot(p.meal_slot)),
                }
                for p in plans
                if expand_plan_slot(p.meal_slot)
            ],
        }

    @staticmethod
    def list_subscribed_packages(db: Session, user_id: str):
        results = SubscriptionRepository.get_subscribed_packages_by_user(db, user_id)
        package_list = []
        for sub_pkg, pkg, sub in results:
            primary_image = next((i.image_url for i in pkg.images if i.is_primary), None)
            package_list.append({
                "subscription_id": str(sub.subscription_id),
                "subscription_status": sub.status,
                "meal_slot": sub.meal_slot,
                "start_date": str(sub.start_date),
                "end_date": str(sub.end_date),
                "package_id": str(pkg.package_id),
                "category_id": str(pkg.category_reference_id),
                "provider_id": str(sub.vendor_reference_id),
                "package_name": pkg.package_name,
                "short_description": pkg.short_description,
                "meal_type": pkg.meal_type,
                "food_type": pkg.food_type,
                "price": pkg.price,
                "subscription_price": pkg.subscription_price,
                "quantity": sub_pkg.quantity,
                "unit_price": sub_pkg.unit_price,
                "is_available": pkg.is_available,
                "primary_image": primary_image,
            })
        return {"success": True, "total": len(package_list), "packages": package_list}

    # ── Pricing preview ───────────────────────────────────────

    @staticmethod
    def quote(db: Session, user_id: str, payload) -> dict:
        """Exactly what create_subscription would charge, without charging."""

        plan = SubscriptionPlanRepository.get_by_id(db, payload.plan_id)
        if not plan:
            raise DomainError("Subscription plan not found")
        slots = expand_plan_slot(plan.meal_slot)
        if not slots:
            raise DomainError("This plan has an invalid meal slot")

        pincode = None
        if payload.address_id:
            pincode = owned_address(db, user_id, payload.address_id).pin_code

        provider, package = assert_sellable(
            db,
            provider_id=payload.vendor_id,
            package_id=payload.package_id,
            delivery_pincode=pincode,
            for_subscription=True,
        )
        if not package_serves(package.meal_type, slots):
            raise DomainError(f"'{package.package_name}' is not served for {', '.join(slots)}")

        start = payload.start_date or earliest_service_date(slots)
        validate_start(slots, start)
        end, days = resolve_term(plan, start, payload.end_date)

        snapshot = build_quote(
            current_components(db),
            kind="subscription",
            base_unit_price=subscription_unit_price(package),
            quantity=payload.quantity,
            deliveries=days * len(slots),
            discount_percent=plan.discount_percent,
        )

        wallet = ledger.lock_customer_wallet(db, user_id)
        balance = money(wallet.balance)
        total = Decimal(snapshot["total_payable"])
        db.rollback()

        return {
            "success": True,
            "kind": "subscription",
            "provider_id": provider.provider_id,
            "provider_name": provider.business_name,
            "package_id": package.package_id,
            "package_name": package.package_name,
            "plan_id": plan.subscription_plan_id,
            "subscription_type": plan.subscription_type,
            "meal_slot": plan.meal_slot,
            "meal_slots": slots,
            "start_date": start,
            "end_date": end,
            "last_meal_date": end - timedelta(days=1),
            "days": days,
            "free_skips": plan.free_skips or 0,
            "earliest_start_date": earliest_service_date(slots),
            "breakdown": quote_view(snapshot),
            "total_payable": total,
            "wallet_balance": balance,
            "shortfall": max(ZERO, total - balance),
        }

    # ── Create ────────────────────────────────────────────────

    @staticmethod
    def create_subscription(db: Session, user_id: str, payload, idempotency_key: str | None = None):

        if idempotency_key:
            txn_key = f"sub_payment:{user_id}:{idempotency_key}"
            existing = ledger.customer_txn_exists(db, txn_key)
            if existing:
                sub = db.query(Subscription).filter(Subscription.subscription_id == existing.reference_id).first()
                return SubscriptionService._created_response(sub, existing.balance_after, replayed=True)
        else:
            txn_key = None

        plan = SubscriptionPlanRepository.get_by_id(db, payload.plan_id)
        if not plan:
            raise DomainError("Subscription plan not found")
        slots = expand_plan_slot(plan.meal_slot)
        if not slots:
            raise DomainError("This plan has an invalid meal slot")

        address = owned_address(db, user_id, payload.address_id)
        item = payload.items[0]

        provider, package = assert_sellable(
            db,
            provider_id=payload.vendor_id,
            package_id=item.package_id,
            delivery_pincode=address.pin_code,
            for_subscription=True,
            lock_provider=True,
        )
        if not package_serves(package.meal_type, slots):
            raise DomainError(f"'{package.package_name}' is not served for {', '.join(slots)}")

        validate_start(slots, payload.start_date)
        end_date, days = resolve_term(plan, payload.start_date, payload.end_date)

        capacity.assert_room(
            db,
            provider_id=provider.provider_id,
            package_id=package.package_id,
            package_name=package.package_name,
            slots=slots,
            start=payload.start_date,
            end=end_date - timedelta(days=1),
            quantity=item.quantity,
        )

        unit_price = subscription_unit_price(package)
        snapshot = build_quote(
            current_components(db),
            kind="subscription",
            base_unit_price=unit_price,
            quantity=item.quantity,
            deliveries=days * len(slots),
            discount_percent=plan.discount_percent,
        )
        snapshot["plan"] = {
            "plan_id": str(plan.subscription_plan_id),
            "subscription_type": plan.subscription_type,
            "meal_slot": plan.meal_slot,
            "days": days,
            "free_skips": plan.free_skips or 0,
            "discount_percent": str(plan.discount_percent or 0),
        }
        total = Decimal(snapshot["total_payable"])
        if total <= ZERO:
            raise DomainError("This plan cannot be priced. Please contact support.")

        wallet = ledger.lock_customer_wallet(db, user_id)
        if txn_key:
            # The wallet lock serialises this customer's checkouts; a retry that
            # raced the first request sees its payment now and replays it.
            existing = ledger.customer_txn_exists(db, txn_key)
            if existing:
                db.rollback()
                sub = db.query(Subscription).filter(Subscription.subscription_id == existing.reference_id).first()
                return SubscriptionService._created_response(sub, existing.balance_after, replayed=True)
        if money(wallet.balance) < total:
            raise ledger.InsufficientBalance(total, money(wallet.balance))

        subscription = Subscription(
            subscription_id=uuid.uuid4(),
            user_reference_id=user_id,
            vendor_reference_id=provider.provider_id,
            plan_reference_id=plan.subscription_plan_id,
            user_address_reference_id=address.user_address_id,
            status="active",
            meal_slot=plan.meal_slot,
            subscription_type=plan.subscription_type,
            start_date=payload.start_date,
            end_date=end_date,
            free_skips_total=plan.free_skips or 0,
            free_skips_used=0,
            total_amount=Decimal(snapshot["base_amount"]),
            discount_amount=Decimal(snapshot["discount_amount"]),
            charges_amount=Decimal(snapshot["charges_amount"]),
            final_amount=total,
            pricing_snapshot=snapshot,
        )
        db.add(subscription)
        db.flush()
        db.add(SubscriptionPackage(
            subscription_reference_id=subscription.subscription_id,
            package_reference_id=package.package_id,
            quantity=item.quantity,
            unit_price=unit_price,
        ))

        txn = ledger.post_customer(
            db, user_id,
            type="debit",
            amount=total,
            reason="subscription_payment",
            idempotency_key=txn_key or f"sub_payment:{subscription.subscription_id}",
            reference_type="subscription",
            reference_id=subscription.subscription_id,
            description=f"{package.package_name} - {plan.subscription_type} {plan.meal_slot} ({days} days)",
            wallet=wallet,
        )

        # Meals exist immediately, including today's when the plan starts today
        meals.generate_meals(db, subscription)

        CartRepository.delete_by_package_ids(db, user_id, [str(package.package_id)])
        notify.customer(
            db, user_id, "subscription_created", "Subscription confirmed",
            f"{package.package_name} from {provider.business_name} starts on {payload.start_date}.",
            {"subscription_id": str(subscription.subscription_id)},
        )
        db.commit()
        db.refresh(subscription)
        business_event(
            "subscription.created",
            subscription_id=subscription.subscription_id,
            user_id=user_id,
            provider_id=provider.provider_id,
            amount=total,
        )
        return SubscriptionService._created_response(subscription, txn.balance_after)

    @staticmethod
    def _created_response(sub: Subscription, balance_after, replayed: bool = False) -> dict:
        return {
            "success": True,
            "message": "Subscription already created" if replayed else "Subscription created successfully",
            "subscription_id": sub.subscription_id,
            "start_date": sub.start_date,
            "end_date": sub.end_date,
            "total_amount": sub.total_amount,
            "discount_amount": sub.discount_amount,
            "charges_amount": sub.charges_amount,
            "final_amount": sub.final_amount,
            "wallet_balance_after": balance_after,
            "price_breakdown": quote_view(sub.pricing_snapshot) if sub.pricing_snapshot else None,
        }

    # ── Read ──────────────────────────────────────────────────

    @staticmethod
    def get_my_subscriptions(db: Session, user_id: str):
        subscriptions = SubscriptionRepository.get_all_by_user(db, user_id)
        return {
            "success": True,
            "total": len(subscriptions),
            "subscriptions": [subscription_view(db, s) for s in subscriptions],
        }

    @staticmethod
    def get_subscription(db: Session, user_id: str, subscription_id):
        return subscription_view(db, owned_subscription(db, user_id, subscription_id))

    @staticmethod
    def _meal_view(order: Order, sub: Subscription) -> dict:
        today = today_local()
        # The hand-over code is shown only on the day of the meal
        show_code = order.order_date == today and order.status in ("scheduled", "preparing", "out_for_delivery")
        free_skips_left = (sub.free_skips_total or 0) - (sub.free_skips_used or 0)
        can_skip = sub.status == "active" and order.status == "scheduled" and order.order_date >= today
        return {
            "order_id": order.order_id,
            "subscription_reference_id": order.subscription_reference_id,
            "vendor_reference_id": order.vendor_reference_id,
            "delivery_address_reference_id": order.delivery_address_reference_id,
            "delivery_boy_reference_id": order.delivery_boy_reference_id,
            "order_date": order.order_date,
            "meal_slot": order.meal_slot,
            "status": order.status,
            "is_free_skip": order.is_free_skip,
            "skip_requested_at": order.skip_requested_at,
            "skip_deadline": cutoff_at(order.order_date, order.meal_slot),
            "delivered_at": order.delivered_at,
            "delivery_notes": order.delivery_notes,
            "cancel_reason": order.cancel_reason,
            "refund_amount": order.refund_amount,
            "otp_for_delivery": order.otp_for_delivery if show_code else None,
            "can_skip": can_skip,
            "skip_will_refund": can_skip and free_skips_left > 0 and is_before_cutoff(order.order_date, order.meal_slot),
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }

    @staticmethod
    def list_subscription_orders(db: Session, user_id: str, subscription_id, status: str = None, order_date: date = None):
        sub = owned_subscription(db, user_id, subscription_id)
        orders = SubscriptionRepository.get_orders_by_subscription(db, sub.subscription_id, status=status, order_date=order_date)
        summary: dict = {}
        for o in orders:
            summary[o.status] = summary.get(o.status, 0) + 1
        return {
            "success": True,
            "subscription_id": sub.subscription_id,
            "subscription_status": sub.status,
            "total": len(orders),
            "status_summary": summary,
            "orders": [SubscriptionService._meal_view(o, sub) for o in orders],
        }

    @staticmethod
    def get_subscription_order(db: Session, user_id: str, subscription_id, order_id):
        sub = owned_subscription(db, user_id, subscription_id)
        row = SubscriptionRepository.get_order_detail_by_id_and_subscription(db, order_id, sub.subscription_id)
        if not row:
            raise HTTPException(status_code=404, detail="Order not found")
        order, address, vendor, delivery_boy = row
        packages = []
        for sub_pkg, pkg in SubscriptionRepository.get_packages_with_menu_by_subscription(db, sub.subscription_id):
            packages.append({
                "package_id": pkg.package_id,
                "package_name": pkg.package_name,
                "meal_type": pkg.meal_type,
                "food_type": pkg.food_type,
                "quantity": sub_pkg.quantity,
                "unit_price": sub_pkg.unit_price,
                "primary_image": next((i.image_url for i in pkg.images if i.is_primary), None),
            })
        return {
            "success": True,
            "order": SubscriptionService._meal_view(order, sub),
            "delivery_address": address,
            "packages": packages,
            "vendor": vendor,
            "delivery_boy": delivery_boy,
        }

    # ── Skip ──────────────────────────────────────────────────

    @staticmethod
    def skip_order(db: Session, user_id: str, subscription_id, order_id):

        sub = owned_subscription(db, user_id, subscription_id, lock=True)
        if sub.status != "active":
            raise DomainError(f"Cannot skip meals of a subscription that is {sub.status}")

        order = (
            db.query(Order)
            .filter(Order.order_id == order_id, Order.subscription_reference_id == sub.subscription_id)
            .with_for_update()
            .first()
        )
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.status != "scheduled":
            raise DomainError(f"Only scheduled meals can be skipped. This meal is {order.status.replace('_', ' ')}")
        if order.order_date < today_local():
            raise DomainError("Past meals cannot be skipped")

        before_cutoff = is_before_cutoff(order.order_date, order.meal_slot)
        free_left = (sub.free_skips_total or 0) - (sub.free_skips_used or 0)
        not_free_reason = None
        if not before_cutoff:
            not_free_reason = "cutoff_passed"
        elif free_left <= 0:
            not_free_reason = "no_free_skips_left"
        is_free = not_free_reason is None

        order.status = "skipped"
        order.is_free_skip = is_free
        order.skip_requested_at = now_utc()
        order.skip_deadline = cutoff_at(order.order_date, order.meal_slot)

        refund = ZERO
        if is_free:
            sub.free_skips_used = (sub.free_skips_used or 0) + 1
            refund = meals.refund_meal(
                db, order, sub,
                reason="free_skip_refund",
                description=f"Free skip refund - {order.meal_slot} on {order.order_date}",
            )

        notify.delivery_partner(
            db, order.delivery_boy_reference_id, "schedule_update", "Delivery skipped by customer",
            f"The {order.meal_slot} delivery on {order.order_date} was skipped by the customer.",
            {"order_id": str(order.order_id), "kind": "subscription"},
        )
        db.commit()

        wallet = ledger.lock_customer_wallet(db, user_id)
        balance = money(wallet.balance)
        db.rollback()

        cutoff_label = SLOT_CUTOFFS[order.meal_slot].strftime("%I:%M %p").lstrip("0")
        if is_free:
            message = f"Meal skipped. Rs {refund} refunded to your wallet as a free skip"
        elif not_free_reason == "cutoff_passed":
            message = f"Meal skipped. The free-skip cut-off for {order.meal_slot} ({cutoff_label}) has passed, so no refund was issued"
        else:
            message = "Meal skipped. No free skips left on this subscription, so no refund was issued"

        return {
            "success": True,
            "message": message,
            "order_id": order.order_id,
            "status": order.status,
            "is_free_skip": is_free,
            "not_free_reason": not_free_reason,
            "skip_deadline": order.skip_deadline,
            "refund_amount": refund,
            "wallet_balance_after": balance,
            "free_skips_total": sub.free_skips_total or 0,
            "free_skips_used": sub.free_skips_used or 0,
            "free_skips_remaining": (sub.free_skips_total or 0) - (sub.free_skips_used or 0),
        }

    # ── Cancel ────────────────────────────────────────────────

    @staticmethod
    def cancel(db: Session, sub: Subscription, *, reason: str, actor: str) -> dict:
        """Cancel a subscription and refund every meal that has not started."""

        if sub.status not in ("active", "paused"):
            raise DomainError(f"Subscription is already {sub.status}")

        count, refunded = meals.cancel_future_meals(
            db, sub,
            from_date=today_local(),
            reason="subscription_cancelled",
            refund=True,
            refund_reason="subscription_cancel_refund",
        )
        # Meals cancelled earlier by a pause were never delivered either
        paused = (
            db.query(Order)
            .filter(
                Order.subscription_reference_id == sub.subscription_id,
                Order.status == "cancelled",
                Order.cancel_reason == "paused",
            )
            .with_for_update()
            .all()
        )
        for meal in paused:
            meal.cancel_reason = "subscription_cancelled"
            refunded += meals.refund_meal(
                db, meal, sub,
                reason="subscription_cancel_refund",
                description=f"Refund for cancelled {meal.meal_slot} on {meal.order_date}",
            )
            count += 1

        sub.status = "cancelled"
        sub.cancelled_at = now_utc()
        sub.cancel_reason = reason
        sub.pause_start_date = None
        notify.customer(
            db, sub.user_reference_id, "subscription_cancelled", "Subscription cancelled",
            f"{count} upcoming meal(s) cancelled. Rs {refunded} refunded to your wallet.",
            {"subscription_id": str(sub.subscription_id)},
        )
        business_event("subscription.cancelled", subscription_id=sub.subscription_id, by=actor, refunded=refunded)
        return {"cancelled_meals": count, "refund_amount": refunded}

    @staticmethod
    def cancel_subscription(db: Session, user_id: str, subscription_id, payload):
        sub = owned_subscription(db, user_id, subscription_id, lock=True)
        result = SubscriptionService.cancel(db, sub, reason=(payload.cancel_reason or "Cancelled by customer"), actor="customer")
        db.commit()
        return {
            "success": True,
            "message": f"Subscription cancelled. Rs {result['refund_amount']} refunded to your wallet.",
            **result,
        }

    # ── Pause / resume ────────────────────────────────────────

    @staticmethod
    def pause_subscription(db: Session, user_id: str, subscription_id):
        sub = owned_subscription(db, user_id, subscription_id, lock=True)
        if sub.status != "active":
            raise DomainError(f"Cannot pause a subscription that is {sub.status}")

        pause_start = today_local() + timedelta(days=1)
        if pause_start >= sub.end_date:
            raise DomainError("Your subscription ends before the pause would take effect")

        meals.cancel_future_meals(db, sub, from_date=pause_start, reason="paused", refund=False)
        sub.status = "paused"
        sub.pause_start_date = pause_start
        db.commit()
        return {
            "success": True,
            "message": "Subscription paused. Meals stop from tomorrow; the end date moves forward when you resume.",
            "pause_start_date": str(pause_start),
        }

    @staticmethod
    def resume_subscription(db: Session, user_id: str, subscription_id):
        sub = owned_subscription(db, user_id, subscription_id, lock=True)
        if sub.status != "paused":
            raise DomainError("Only a paused subscription can be resumed")

        resume_date = today_local() + timedelta(days=1)
        days_paused = max(0, (resume_date - sub.pause_start_date).days)
        old_end = sub.end_date
        new_end = old_end + timedelta(days=days_paused)
        slots = expand_plan_slot(sub.meal_slot)

        # Lock the kitchen and check room on the dates coming back
        db.query(Provider).filter(Provider.provider_id == sub.vendor_reference_id).with_for_update().first()
        package_row = db.query(SubscriptionPackage).filter(
            SubscriptionPackage.subscription_reference_id == sub.subscription_id
        ).first()
        if days_paused and package_row:
            capacity.assert_room(
                db,
                provider_id=sub.vendor_reference_id,
                package_id=package_row.package_reference_id,
                package_name="Your package",
                slots=slots,
                start=old_end,
                end=new_end - timedelta(days=1),
                quantity=package_row.quantity,
            )

        restored = (
            db.query(Order)
            .filter(
                Order.subscription_reference_id == sub.subscription_id,
                Order.order_date >= resume_date,
                Order.status == "cancelled",
                Order.cancel_reason == "paused",
            )
            .with_for_update()
            .all()
        )
        for meal in restored:
            meal.status = "scheduled"
            meal.cancel_reason = None

        # Meals missed while paused are made up by extending the end date, so
        # they are no longer owed as a refund if the plan is cancelled later.
        db.query(Order).filter(
            Order.subscription_reference_id == sub.subscription_id,
            Order.status == "cancelled",
            Order.cancel_reason == "paused",
            Order.order_date < resume_date,
        ).update({"cancel_reason": "paused_extended"}, synchronize_session=False)

        # Meals between the pause start and tomorrow stay cancelled: the
        # subscription is extended by exactly that many days instead.
        sub.status = "active"
        sub.end_date = new_end
        sub.total_days_paused = (sub.total_days_paused or 0) + days_paused
        sub.pause_start_date = None
        created = meals.generate_meals(db, sub, from_date=resume_date)
        db.commit()

        return {
            "success": True,
            "message": "Subscription resumed",
            "resume_date": str(resume_date),
            "new_end_date": str(new_end),
            "days_paused": days_paused,
            "new_orders_created": created,
        }
