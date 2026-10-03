"""
Package switch during an active subscription (Package Switch Policy).

Unused Service Value Method:
  remaining value  = meals still to come on the old plan (from the effective
                     date) x the value of one old meal (from its snapshot)
  new cost         = the pricing engine's price for the same number of days
                     and meals on the new package (same plan discount)
  difference       = new cost - remaining value; paid from or credited to the
                     wallet after truncating to whole rupees (Floor Rule)

The switch takes effect from tomorrow (or from the start date when the plan
has not started). The new subscription stores what was actually paid, so its
own skips and cancellation refunds stay exact.
"""

import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_FLOOR

from sqlalchemy.orm import Session

from app.core.audit import business_event
from app.core.clock import today_local
from app.core.errors import DomainError
from app.domain import capacity, ledger, notify, orders as meals
from app.domain.eligibility import assert_sellable
from app.domain.pricing import build_quote, current_components, subscription_unit_price, money, floor_money, ZERO
from app.domain.slots import expand_plan_slot, package_serves
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.package_switch_log_model import PackageSwitchLog
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.subscription_plan_model import SubscriptionPlan
from app.models.user_address_model import UserAddress
from app.services.subscription_service import owned_subscription

WHOLE_RUPEE = Decimal("1")


def _floor_rupees(amount: Decimal) -> Decimal:
    return amount.quantize(WHOLE_RUPEE, rounding=ROUND_FLOOR)


class PackageSwitchService:

    @staticmethod
    def _resolve(db: Session, user_id: str, subscription_id, payload, lock: bool):

        sub = owned_subscription(db, user_id, subscription_id, lock=lock)
        if sub.status != "active":
            raise DomainError(f"Cannot switch a subscription that is {sub.status}")

        old_pkg = db.query(SubscriptionPackage).filter(
            SubscriptionPackage.subscription_reference_id == sub.subscription_id
        ).first()
        if old_pkg is None:
            raise DomainError("Subscription has no package")
        if payload.old_package_id and str(payload.old_package_id) != str(old_pkg.package_reference_id):
            raise DomainError("old_package_id does not belong to this subscription")

        new_package = db.query(MenuPackage).filter(MenuPackage.package_id == payload.new_package_id).first()
        if new_package is None:
            raise DomainError("New package not found or unavailable")
        new_provider_id = payload.new_provider_id or (None if new_package.is_predefined else new_package.provider_id)
        if new_provider_id is None:
            raise DomainError("new_provider_id is required for Orleeno catalogue packages")

        if (
            str(new_package.package_id) == str(old_pkg.package_reference_id)
            and str(new_provider_id) == str(sub.vendor_reference_id)
        ):
            raise DomainError("You are already subscribed to this package.")

        address = db.query(UserAddress).filter(UserAddress.user_address_id == sub.user_address_reference_id).first()
        provider, new_package = assert_sellable(
            db,
            provider_id=new_provider_id,
            package_id=new_package.package_id,
            delivery_pincode=address.pin_code if address else None,
            for_subscription=True,
            lock_provider=lock,
        )

        slots = expand_plan_slot(sub.meal_slot)
        if not package_serves(new_package.meal_type, slots):
            raise DomainError(f"'{new_package.package_name}' is not served for {', '.join(slots)}")

        today = today_local()
        effective = max(today + timedelta(days=1), sub.start_date)
        remaining_days = (sub.end_date - effective).days
        if remaining_days < 1:
            raise DomainError(
                "Package switch is not allowed on the last day of the subscription. "
                "You may purchase a new subscription instead."
            )

        remaining_meals = (
            db.query(Order)
            .filter(
                Order.subscription_reference_id == sub.subscription_id,
                Order.order_date >= effective,
                Order.status == "scheduled",
            )
            .count()
        )
        old_meal_value = meals.meal_value(sub)
        remaining_value = money(old_meal_value * remaining_meals)

        discount = (sub.pricing_snapshot or {}).get("discount_percent")
        if discount is None:
            plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.subscription_plan_id == sub.plan_reference_id).first()
            discount = plan.discount_percent if plan else 0

        quote = build_quote(
            current_components(db),
            kind="subscription",
            base_unit_price=subscription_unit_price(new_package),
            quantity=old_pkg.quantity,
            deliveries=remaining_days * len(slots),
            discount_percent=discount,
        )
        new_cost = Decimal(quote["total_payable"])
        adjustment = new_cost - remaining_value

        if adjustment > 0:
            payment, credit = _floor_rupees(adjustment), ZERO
            action = "payment_required" if payment > 0 else "no_adjustment"
        elif adjustment < 0:
            payment, credit = ZERO, _floor_rupees(-adjustment)
            action = "wallet_credit" if credit > 0 else "no_adjustment"
        else:
            payment, credit, action = ZERO, ZERO, "no_adjustment"

        total_days = (sub.end_date - sub.start_date).days
        return {
            "subscription": sub,
            "old_sub_pkg": old_pkg,
            "new_package": new_package,
            "new_provider": provider,
            "slots": slots,
            "quote": quote,
            "switch_request_date": today,
            "effective_date": effective,
            "total_days": total_days,
            "used_days": max(0, total_days - remaining_days),
            "remaining_days": remaining_days,
            "remaining_meals": remaining_meals,
            "old_daily_cost": money(old_meal_value * len(slots)),
            "new_daily_cost": money(new_cost / remaining_days),
            "remaining_value": remaining_value,
            "new_remaining_cost": new_cost,
            "adjustment_amount": adjustment,
            "payment_amount": payment,
            "wallet_credit_amount": credit,
            "action": action,
        }

    @staticmethod
    def _calculation(calc: dict) -> dict:
        keys = (
            "switch_request_date", "effective_date", "total_days", "used_days", "remaining_days",
            "old_daily_cost", "new_daily_cost", "remaining_value", "new_remaining_cost",
            "adjustment_amount", "payment_amount", "wallet_credit_amount", "action",
        )
        return {k: calc[k] for k in keys}

    @staticmethod
    def preview_switch(db: Session, user_id: str, subscription_id, payload):
        calc = PackageSwitchService._resolve(db, user_id, subscription_id, payload, lock=False)
        sub = calc["subscription"]
        old_package = db.query(MenuPackage).filter(MenuPackage.package_id == calc["old_sub_pkg"].package_reference_id).first()
        wallet = ledger.lock_customer_wallet(db, user_id)
        balance = money(wallet.balance)
        db.rollback()
        return {
            "success": True,
            "old_package_id": calc["old_sub_pkg"].package_reference_id,
            "old_package_name": old_package.package_name if old_package else "",
            "old_provider_id": sub.vendor_reference_id,
            "new_package_id": calc["new_package"].package_id,
            "new_package_name": calc["new_package"].package_name,
            "new_provider_id": calc["new_provider"].provider_id,
            "calculation": PackageSwitchService._calculation(calc),
            "wallet_balance": balance,
        }

    @staticmethod
    def switch_package(db: Session, user_id: str, subscription_id, payload):
        calc = PackageSwitchService._resolve(db, user_id, subscription_id, payload, lock=True)
        sub: Subscription = calc["subscription"]
        new_package = calc["new_package"]
        provider = calc["new_provider"]
        effective = calc["effective_date"]
        new_end = effective + timedelta(days=calc["remaining_days"])

        capacity.assert_room(
            db,
            provider_id=provider.provider_id,
            package_id=new_package.package_id,
            package_name=new_package.package_name,
            slots=calc["slots"],
            start=effective,
            end=new_end - timedelta(days=1),
            quantity=calc["old_sub_pkg"].quantity,
        )

        wallet = ledger.lock_customer_wallet(db, user_id)
        if calc["payment_amount"] > 0 and money(wallet.balance) < calc["payment_amount"]:
            raise ledger.InsufficientBalance(calc["payment_amount"], money(wallet.balance))

        # 1. Close the old plan: its future meals move to the new one
        meals.cancel_future_meals(db, sub, from_date=effective, reason="switched", refund=False)
        affected = {
            o.delivery_boy_reference_id
            for o in db.query(Order).filter(
                Order.subscription_reference_id == sub.subscription_id,
                Order.cancel_reason == "switched",
                Order.delivery_boy_reference_id.isnot(None),
            ).all()
        }
        sub.status = "switched"
        if effective > sub.start_date:
            sub.end_date = effective
        sub.notes = f"Switched to '{new_package.package_name}' from {effective}"

        # 2. The new plan, priced by the engine; it records what was really paid
        paid = calc["remaining_value"] + calc["payment_amount"] - calc["wallet_credit_amount"]
        snapshot = dict(calc["quote"])
        snapshot["settlement"] = dict(snapshot["settlement"])
        deliveries = int(snapshot["deliveries"])
        snapshot["settlement"]["customer_payable_per_delivery"] = str(floor_money(paid / deliveries))
        snapshot["switched_from"] = str(sub.subscription_id)
        snapshot["plan"] = (sub.pricing_snapshot or {}).get("plan")
        if paid <= ZERO:
            raise DomainError("This switch cannot be priced. Please contact support.")

        new_sub = Subscription(
            subscription_id=uuid.uuid4(),
            user_reference_id=sub.user_reference_id,
            vendor_reference_id=provider.provider_id,
            plan_reference_id=sub.plan_reference_id,
            user_address_reference_id=sub.user_address_reference_id,
            status="active",
            meal_slot=sub.meal_slot,
            subscription_type=sub.subscription_type,
            start_date=effective,
            end_date=new_end,
            free_skips_total=sub.free_skips_total,
            free_skips_used=sub.free_skips_used,
            total_amount=Decimal(snapshot["base_amount"]),
            discount_amount=Decimal(snapshot["discount_amount"]),
            charges_amount=Decimal(snapshot["charges_amount"]),
            final_amount=paid,
            pricing_snapshot=snapshot,
        )
        db.add(new_sub)
        db.flush()
        db.add(SubscriptionPackage(
            subscription_reference_id=new_sub.subscription_id,
            package_reference_id=new_package.package_id,
            quantity=calc["old_sub_pkg"].quantity,
            unit_price=Decimal(snapshot["base_unit_price"]),
        ))

        # 3. Move the money (Floor Rule already applied)
        log_id = uuid.uuid4()
        if calc["payment_amount"] > 0:
            ledger.post_customer(
                db, user_id, type="debit", amount=calc["payment_amount"], reason="package_switch_payment",
                idempotency_key=f"switch_payment:{log_id}", reference_type="subscription",
                reference_id=new_sub.subscription_id, wallet=wallet,
                description=f"Package switch to '{new_package.package_name}' from {effective}",
            )
            payment_status = "paid"
        elif calc["wallet_credit_amount"] > 0:
            ledger.post_customer(
                db, user_id, type="credit", amount=calc["wallet_credit_amount"], reason="package_switch_credit",
                idempotency_key=f"switch_credit:{log_id}", reference_type="subscription",
                reference_id=new_sub.subscription_id, wallet=wallet,
                description=f"Package switch credit - '{new_package.package_name}' from {effective}",
            )
            sub.refunded_amount = money(sub.refunded_amount) + calc["wallet_credit_amount"]
            payment_status = "credited"
        else:
            payment_status = "not_required"

        created = meals.generate_meals(db, new_sub)

        db.add(PackageSwitchLog(
            package_switch_log_id=log_id,
            user_reference_id=sub.user_reference_id,
            old_subscription_reference_id=sub.subscription_id,
            new_subscription_reference_id=new_sub.subscription_id,
            old_provider_reference_id=sub.vendor_reference_id,
            new_provider_reference_id=provider.provider_id,
            old_package_reference_id=calc["old_sub_pkg"].package_reference_id,
            new_package_reference_id=new_package.package_id,
            switch_request_date=calc["switch_request_date"],
            effective_date=effective,
            total_days=calc["total_days"],
            used_days=calc["used_days"],
            remaining_days=calc["remaining_days"],
            old_daily_cost=calc["old_daily_cost"],
            new_daily_cost=calc["new_daily_cost"],
            remaining_value=calc["remaining_value"],
            new_remaining_cost=calc["new_remaining_cost"],
            adjustment_amount=calc["adjustment_amount"],
            payment_amount=calc["payment_amount"],
            wallet_credit_amount=calc["wallet_credit_amount"],
            payment_status=payment_status,
            switch_status="completed",
            created_by="user",
        ))

        if payment_status == "paid":
            money_line = f"You paid Rs {calc['payment_amount']}."
        elif payment_status == "credited":
            money_line = f"Rs {calc['wallet_credit_amount']} was credited to your wallet."
        else:
            money_line = "No payment was required."
        notify.customer(
            db, user_id, "package_switch", "Package switched successfully",
            f"Your meals switch to '{new_package.package_name}' by {provider.business_name} from {effective}. {money_line}",
            {
                "old_subscription_id": str(sub.subscription_id),
                "new_subscription_id": str(new_sub.subscription_id),
                "effective_date": str(effective),
            },
        )
        for boy in affected:
            notify.delivery_partner(
                db, boy, "schedule_update", "Delivery schedule updated",
                f"Deliveries for a subscription were reassigned from {effective}. Please check your order list.",
                {"effective_date": str(effective)},
            )

        db.commit()
        business_event("subscription.switched", old=sub.subscription_id, new=new_sub.subscription_id, payment=calc["payment_amount"], credit=calc["wallet_credit_amount"])

        wallet = ledger.lock_customer_wallet(db, user_id)
        balance = money(wallet.balance)
        db.rollback()

        return {
            "success": True,
            "message": "Package switched successfully",
            "switch_id": log_id,
            "old_subscription_id": sub.subscription_id,
            "new_subscription_id": new_sub.subscription_id,
            "new_provider_id": provider.provider_id,
            "effective_date": effective,
            "payment_amount": calc["payment_amount"],
            "wallet_credit_amount": calc["wallet_credit_amount"],
            "wallet_balance_after": balance,
            "new_orders_created": created,
        }
