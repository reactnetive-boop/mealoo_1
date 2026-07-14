"""
Package switch during an active subscription (Mealoo Package Switch Policy).

Implements the Unused Service Value Method: only the remaining (unused) value
of the current subscription is compared with the remaining cost of the new
package. The switch becomes effective from the next service day. Monetary
movements follow the Floor (Truncate) Rule — fractional paise are discarded.
"""

import uuid
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.order_model import Order
from app.models.package_switch_log_model import PackageSwitchLog
from app.models.provider_model import Provider
from app.repositories.menu_repository import MenuRepository
from app.repositories.package_capacity_repository import PackageCapacityRepository
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.wallet_repository import WalletRepository
from app.repositories.delivery_boy_repository import DeliveryBoyRepository
from app.services.notification_service import NotificationService
from app.services.subscription_service import (
    MEAL_SLOT_MULTIPLIER,
    MEAL_SLOT_EXPANSION,
)

TWO_PLACES = Decimal("0.01")
WHOLE_RUPEE = Decimal("1")


def _floor_rupees(amount: Decimal) -> Decimal:
    """Policy §17: truncate to the nearest lower whole rupee."""
    return amount.quantize(WHOLE_RUPEE, rounding=ROUND_FLOOR)


class PackageSwitchService:

    # ── Calculation ───────────────────────────────────────

    @staticmethod
    def _resolve_switch(db: Session, user_id: str, subscription_id, payload):
        subscription = SubscriptionRepository.get_by_id(db, subscription_id)

        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        if str(subscription.user_reference_id) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        if subscription.status != "active":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot switch a subscription that is {subscription.status}"
            )

        # Old package: the subscription's package (old_package_id required
        # only when the subscription holds more than one package)
        packages = subscription.packages

        if not packages:
            raise HTTPException(status_code=400, detail="Subscription has no packages")

        if payload.old_package_id:
            old_sub_pkg = next(
                (p for p in packages
                 if str(p.package_reference_id) == str(payload.old_package_id)),
                None
            )
            if not old_sub_pkg:
                raise HTTPException(
                    status_code=400,
                    detail="old_package_id does not belong to this subscription"
                )
        elif len(packages) == 1:
            old_sub_pkg = packages[0]
        else:
            raise HTTPException(
                status_code=400,
                detail="Subscription has multiple packages — provide old_package_id"
            )

        old_package = MenuRepository.get_active_package_by_id(
            db, old_sub_pkg.package_reference_id
        )

        # Same package selected (policy §15)
        if str(payload.new_package_id) == str(old_sub_pkg.package_reference_id):
            raise HTTPException(
                status_code=400,
                detail="You are already subscribed to this package."
            )

        # New package must exist, be available, and allow subscriptions
        new_package = MenuRepository.get_active_package_by_id(db, payload.new_package_id)

        if not new_package:
            raise HTTPException(
                status_code=400,
                detail="New package not found or unavailable"
            )

        if not new_package.is_subscription_available:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Package '{new_package.package_name}' "
                    f"is not available for subscription"
                )
            )

        plan = SubscriptionPlanRepository.get_by_id(db, subscription.plan_reference_id)

        if not plan:
            raise HTTPException(status_code=400, detail="Subscription plan not found")

        # ── Effective date rule (policy §2): never same-day ──
        today = date.today()

        if today < subscription.start_date:
            # Subscription hasn't started serving yet
            effective_date = subscription.start_date
            used_days = 0
        else:
            effective_date = today + timedelta(days=1)
            used_days = (today - subscription.start_date).days + 1

        total_days = (subscription.end_date - subscription.start_date).days
        remaining_days = total_days - used_days

        # Switch on last day is not allowed (policy §15)
        if remaining_days < 1:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Package switch is not allowed on the last day of the "
                    "subscription. You may purchase a new subscription instead."
                )
            )

        # ── Unused Service Value Method (policy §4/§16) ──
        old_daily_cost = (
            Decimal(str(subscription.final_amount)) / Decimal(total_days)
        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        remaining_value = (old_daily_cost * remaining_days).quantize(TWO_PLACES)

        # New package cost over the same plan (same duration, slot, discount)
        quantity = old_sub_pkg.quantity
        multiplier = MEAL_SLOT_MULTIPLIER.get(subscription.meal_slot, 1)

        new_effective_price = (
            Decimal(str(new_package.price)) - Decimal(str(new_package.discounted_price))
            if new_package.discounted_price
            else Decimal(str(new_package.price))
        )

        new_total_full = new_effective_price * quantity * multiplier * total_days
        new_discount_full = (
            new_total_full * Decimal(str(plan.discount_percent)) / 100
        ).quantize(TWO_PLACES)
        new_final_full = new_total_full - new_discount_full

        new_daily_cost = (
            new_final_full / Decimal(total_days)
        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        new_remaining_cost = (new_daily_cost * remaining_days).quantize(TWO_PLACES)

        adjustment_amount = new_remaining_cost - remaining_value

        # Floor rule (policy §17) on the amount actually moved
        if adjustment_amount > 0:
            payment_amount = _floor_rupees(adjustment_amount)
            wallet_credit_amount = Decimal("0")
            action = "payment_required" if payment_amount > 0 else "no_adjustment"
        elif adjustment_amount < 0:
            payment_amount = Decimal("0")
            wallet_credit_amount = _floor_rupees(-adjustment_amount)
            action = "wallet_credit" if wallet_credit_amount > 0 else "no_adjustment"
        else:
            payment_amount = Decimal("0")
            wallet_credit_amount = Decimal("0")
            action = "no_adjustment"

        return {
            "subscription": subscription,
            "plan": plan,
            "old_sub_pkg": old_sub_pkg,
            "old_package": old_package,
            "new_package": new_package,
            "quantity": quantity,
            "multiplier": multiplier,
            "new_effective_price": new_effective_price,
            "switch_request_date": today,
            "effective_date": effective_date,
            "total_days": total_days,
            "used_days": used_days,
            "remaining_days": remaining_days,
            "old_daily_cost": old_daily_cost,
            "new_daily_cost": new_daily_cost,
            "remaining_value": remaining_value,
            "new_remaining_cost": new_remaining_cost,
            "adjustment_amount": adjustment_amount,
            "payment_amount": payment_amount,
            "wallet_credit_amount": wallet_credit_amount,
            "action": action,
        }

    @staticmethod
    def _calculation_payload(calc: dict) -> dict:
        return {
            "switch_request_date": calc["switch_request_date"],
            "effective_date": calc["effective_date"],
            "total_days": calc["total_days"],
            "used_days": calc["used_days"],
            "remaining_days": calc["remaining_days"],
            "old_daily_cost": calc["old_daily_cost"],
            "new_daily_cost": calc["new_daily_cost"],
            "remaining_value": calc["remaining_value"],
            "new_remaining_cost": calc["new_remaining_cost"],
            "adjustment_amount": calc["adjustment_amount"],
            "payment_amount": calc["payment_amount"],
            "wallet_credit_amount": calc["wallet_credit_amount"],
            "action": calc["action"],
        }

    # ── Preview ───────────────────────────────────────────

    @staticmethod
    def preview_switch(db: Session, user_id: str, subscription_id, payload):
        calc = PackageSwitchService._resolve_switch(db, user_id, subscription_id, payload)

        wallet = WalletRepository.get_or_create(db, user_id)
        db.commit()

        subscription = calc["subscription"]
        old_package = calc["old_package"]
        new_package = calc["new_package"]

        return {
            "success": True,
            "old_package_id": calc["old_sub_pkg"].package_reference_id,
            "old_package_name": old_package.package_name if old_package else "",
            "old_provider_id": subscription.vendor_reference_id,
            "new_package_id": new_package.package_id,
            "new_package_name": new_package.package_name,
            "new_provider_id": new_package.provider_id,
            "calculation": PackageSwitchService._calculation_payload(calc),
            "wallet_balance": Decimal(str(wallet.balance)),
        }

    # ── Execute ───────────────────────────────────────────

    @staticmethod
    def switch_package(db: Session, user_id: str, subscription_id, payload):
        calc = PackageSwitchService._resolve_switch(db, user_id, subscription_id, payload)

        subscription = calc["subscription"]
        plan = calc["plan"]
        new_package = calc["new_package"]
        effective_date = calc["effective_date"]
        remaining_days = calc["remaining_days"]
        payment_amount = calc["payment_amount"]
        wallet_credit_amount = calc["wallet_credit_amount"]

        # Capacity check on the new provider for the remaining period (policy §15)
        individual_slots = MEAL_SLOT_EXPANSION.get(
            subscription.meal_slot, [subscription.meal_slot]
        )

        PackageCapacityRepository.check_and_raise_subscription(
            db=db,
            vendor_id=new_package.provider_id,
            package_id=new_package.package_id,
            package_name=new_package.package_name,
            requested_qty=calc["quantity"],
            individual_slots=individual_slots,
        )

        # Payment rule (policy §10): upgrade must be paid before the switch
        wallet = WalletRepository.get_or_create(db, user_id)

        if payment_amount > 0 and Decimal(str(wallet.balance)) < payment_amount:
            # Payment failure → switch request is cancelled, nothing changes
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Insufficient wallet balance for the switch payment. "
                    f"Required: {payment_amount}, Available: {wallet.balance}. "
                    f"The switch request has been cancelled."
                )
            )

        try:
            # 1. Close the old subscription after today's service
            subscription.status = "switched"
            subscription.end_date = effective_date
            subscription.notes = (
                f"Switched to package '{new_package.package_name}' "
                f"effective {effective_date}"
            )
            db.flush()

            # 2. Cancel old future orders; remember affected delivery boys
            future_orders = (
                db.query(Order)
                .filter(
                    Order.subscription_reference_id == subscription.subscription_id,
                    Order.order_date >= effective_date,
                    Order.status == "scheduled"
                )
                .all()
            )

            affected_delivery_boys = {
                o.delivery_boy_reference_id
                for o in future_orders
                if o.delivery_boy_reference_id
            }

            for order in future_orders:
                order.status = "cancelled"

            db.flush()

            # 3. Create the new subscription for the remaining period
            new_end_date = effective_date + timedelta(days=remaining_days)

            new_total = (
                calc["new_effective_price"] * calc["quantity"]
                * calc["multiplier"] * remaining_days
            )
            new_discount = (
                new_total * Decimal(str(plan.discount_percent)) / 100
            ).quantize(TWO_PLACES)
            new_final = calc["new_remaining_cost"]

            new_subscription = SubscriptionRepository.create(db, {
                "user_reference_id": subscription.user_reference_id,
                "vendor_reference_id": new_package.provider_id,
                "plan_reference_id": subscription.plan_reference_id,
                "user_address_reference_id": subscription.user_address_reference_id,
                "status": "active",
                "meal_slot": subscription.meal_slot,
                "subscription_type": subscription.subscription_type,
                "start_date": effective_date,
                "end_date": new_end_date,
                "free_skips_total": subscription.free_skips_total,
                "free_skips_used": subscription.free_skips_used,
                "total_amount": new_total,
                "discount_amount": new_discount,
                "final_amount": new_final,
            })

            SubscriptionRepository.create_package(db, {
                "subscription_reference_id": new_subscription.subscription_id,
                "package_reference_id": str(new_package.package_id),
                "quantity": calc["quantity"],
                "unit_price": calc["new_effective_price"],
            })

            # 4. Move the money (floor rule already applied)
            balance_before = Decimal(str(wallet.balance))

            if payment_amount > 0:
                WalletRepository.deduct_balance(db, wallet, payment_amount)
                WalletRepository.create_transaction(db, {
                    "wallet_reference_id": str(wallet.wallet_id),
                    "user_reference_id": user_id,
                    "type": "debit",
                    "reason": "package_switch_payment",
                    "amount": payment_amount,
                    "balance_before": balance_before,
                    "balance_after": Decimal(str(wallet.balance)),
                    "reference_id": new_subscription.subscription_id,
                    "reference_type": "subscription",
                    "description": (
                        f"Package switch upgrade payment — "
                        f"'{new_package.package_name}' from {effective_date}"
                    ),
                })
                payment_status = "paid"
            elif wallet_credit_amount > 0:
                WalletRepository.credit_balance(db, wallet, wallet_credit_amount)
                WalletRepository.create_transaction(db, {
                    "wallet_reference_id": str(wallet.wallet_id),
                    "user_reference_id": user_id,
                    "type": "credit",
                    "reason": "package_switch_credit",
                    "amount": wallet_credit_amount,
                    "balance_before": balance_before,
                    "balance_after": Decimal(str(wallet.balance)),
                    "reference_id": new_subscription.subscription_id,
                    "reference_type": "subscription",
                    "description": (
                        f"Package switch downgrade credit — "
                        f"'{new_package.package_name}' from {effective_date}"
                    ),
                })
                payment_status = "credited"
            else:
                payment_status = "not_required"

            # 5. Create orders for the new subscription period
            new_orders = []
            current_date = effective_date

            while current_date < new_end_date:
                for slot in individual_slots:
                    new_orders.append({
                        "order_id": uuid.uuid4(),
                        "subscription_reference_id": new_subscription.subscription_id,
                        "user_reference_id": new_subscription.user_reference_id,
                        "vendor_reference_id": new_subscription.vendor_reference_id,
                        "delivery_address_reference_id": new_subscription.user_address_reference_id,
                        "order_date": current_date,
                        "meal_slot": slot,
                        "status": "scheduled",
                        "is_free_skip": False,
                        "otp_for_delivery": str(random.randint(100000, 999999)),
                    })
                current_date += timedelta(days=1)

            if new_orders:
                db.bulk_insert_mappings(Order, new_orders)

            # 6. Audit trail (policy §14)
            switch_log = PackageSwitchLog(
                user_reference_id=subscription.user_reference_id,
                old_subscription_reference_id=subscription.subscription_id,
                new_subscription_reference_id=new_subscription.subscription_id,
                old_provider_reference_id=subscription.vendor_reference_id,
                new_provider_reference_id=new_package.provider_id,
                old_package_reference_id=calc["old_sub_pkg"].package_reference_id,
                new_package_reference_id=new_package.package_id,
                switch_request_date=calc["switch_request_date"],
                effective_date=effective_date,
                total_days=calc["total_days"],
                used_days=calc["used_days"],
                remaining_days=remaining_days,
                old_daily_cost=calc["old_daily_cost"],
                new_daily_cost=calc["new_daily_cost"],
                remaining_value=calc["remaining_value"],
                new_remaining_cost=calc["new_remaining_cost"],
                adjustment_amount=calc["adjustment_amount"],
                payment_amount=payment_amount,
                wallet_credit_amount=wallet_credit_amount,
                payment_status=payment_status,
                switch_status="completed",
                created_by="user",
            )
            db.add(switch_log)
            db.flush()

            db.commit()

        except HTTPException:
            db.rollback()
            raise

        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Package switch failed: {str(e)}"
            )

        # ── Post-commit notifications (policy §13, non-fatal) ──
        try:
            new_provider = (
                db.query(Provider)
                .filter(Provider.provider_id == new_package.provider_id)
                .first()
            )
            provider_name = new_provider.business_name if new_provider else "your new provider"

            if payment_status == "paid":
                money_line = f"You paid ₹{payment_amount}."
            elif payment_status == "credited":
                money_line = f"₹{wallet_credit_amount} was credited to your wallet."
            else:
                money_line = "No payment was required."

            NotificationService.create_notification(
                db,
                user_id=user_id,
                type="package_switch",
                title="Package switched successfully",
                body=(
                    f"Your meals switch to '{new_package.package_name}' by "
                    f"{provider_name} from {effective_date}. {money_line}"
                ),
                data={
                    "old_subscription_id": str(subscription.subscription_id),
                    "new_subscription_id": str(new_subscription.subscription_id),
                    "new_provider_id": str(new_package.provider_id),
                    "effective_date": str(effective_date),
                },
            )

            for boy_id in affected_delivery_boys:
                DeliveryBoyRepository.create_notification(
                    db,
                    delivery_boy_id=boy_id,
                    type="schedule_update",
                    title="Delivery schedule updated",
                    body=(
                        f"Deliveries for a subscription were reassigned from "
                        f"{effective_date}. Please check your order list."
                    ),
                    data={"effective_date": str(effective_date)},
                )
        except Exception:
            # Notifications must never fail the completed switch
            db.rollback()

        return {
            "success": True,
            "message": "Package switched successfully",
            "switch_id": switch_log.package_switch_log_id,
            "old_subscription_id": subscription.subscription_id,
            "new_subscription_id": new_subscription.subscription_id,
            "new_provider_id": new_package.provider_id,
            "effective_date": effective_date,
            "payment_amount": payment_amount,
            "wallet_credit_amount": wallet_credit_amount,
            "wallet_balance_after": Decimal(str(wallet.balance)),
            "new_orders_created": len(new_orders),
        }
