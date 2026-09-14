import uuid
import random
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.menu_repository import MenuRepository
from app.repositories.user_address_repository import UserAddressRepository
from app.repositories.wallet_repository import WalletRepository
from app.repositories.package_capacity_repository import PackageCapacityRepository
from app.repositories.cart_repository import CartRepository
from app.models.order_model import Order
from app.repositories.delivery_boy_repository import DeliveryBoyRepository


MEAL_SLOT_MULTIPLIER = {
    "breakfast": 1,
    "lunch": 1,
    "dinner": 1,
    "breakfast_lunch": 2,
    "lunch_dinner": 2,
    "breakfast_dinner": 2,
    "all_slots": 3,
}

MEAL_SLOT_EXPANSION = {
    "breakfast":        ["breakfast"],
    "lunch":            ["lunch"],
    "dinner":           ["dinner"],
    "breakfast_lunch":  ["breakfast", "lunch"],
    "lunch_dinner":     ["lunch", "dinner"],
    "breakfast_dinner": ["breakfast", "dinner"],
    "all_slots":        ["breakfast", "lunch", "dinner"],
}

# Same-day skip cutoff per meal slot (server local time). A skip requested at or
# after the cutoff on the order date is still allowed, but is never a free skip.
FREE_SKIP_CUTOFF = {
    "breakfast": time(6, 0),
    "lunch":     time(9, 0),
    "dinner":    time(15, 0),
}


class SubscriptionService:

    @staticmethod
    def get_plan_options(db: Session):
        return {
            "meal_slots": SubscriptionPlanRepository.get_distinct_meal_slots(db),
            "subscription_types": SubscriptionPlanRepository.get_distinct_subscription_types(db)
        }

    @staticmethod
    def list_plans(
        db: Session,
        meal_slot: str = None,
        subscription_type: str = None
    ):

        plans = SubscriptionPlanRepository.get_all_active(
            db,
            meal_slot=meal_slot,
            subscription_type=subscription_type
        )

        return {
            "success": True,
            "total": len(plans),
            "plans": plans
        }

    @staticmethod
    def list_subscribed_packages(
        db: Session,
        user_id: str
    ):

        results = SubscriptionRepository.get_subscribed_packages_by_user(
            db,
            user_id
        )

        package_list = []

        for sub_pkg, pkg, sub in results:

            primary_image = None

            for img in pkg.images:

                if img.is_primary:

                    primary_image = img.image_url

                    break

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
                "primary_image": primary_image
            })

        return {
            "success": True,
            "total": len(package_list),
            "packages": package_list
        }

    @staticmethod
    def create_subscription(
        db: Session,
        user_id: str,
        payload
    ):
        # 1. Validate plan
        plan = SubscriptionPlanRepository.get_by_id(
            db, payload.plan_id
        )

        if not plan:

            raise HTTPException(
                status_code=400,
                detail="Subscription plan not found"
            )

        # 3. Validate address belongs to user
        address = UserAddressRepository.get_by_id(
            db, payload.address_id
        )

        if not address or str(address.user_reference_id) != user_id:

            raise HTTPException(
                status_code=400,
                detail="Invalid delivery address"
            )

        # 4. Validate each package — active, subscription-enabled, belongs to vendor
        resolved_items = []

        for item in payload.items:

            package = MenuRepository.get_active_package_by_id(
                db, item.package_id
            )

            if not package:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Package {item.package_id} "
                        f"not found or unavailable"
                    )
                )

            if not package.is_subscription_available:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Package '{package.package_name}' "
                        f"is not available for subscription"
                    )
                )

            if str(package.provider_id) != str(payload.vendor_id):

                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Package '{package.package_name}' "
                        f"does not belong to the selected provider. "
                        f"All packages must be from the same provider."
                    )
                )

            # Effective daily price per meal = price minus discount amount
            effective_price = (
                Decimal(str(package.price)) - Decimal(str(package.discounted_price))
                if package.discounted_price
                else Decimal(str(package.price))
            )

            resolved_items.append({
                "package_id": package.package_id,
                "package_name": package.package_name,
                "unit_price": effective_price,
                "quantity": item.quantity
            })

        # 5. Check provider daily capacity per package per individual meal slot
        individual_slots = MEAL_SLOT_EXPANSION.get(plan.meal_slot, [plan.meal_slot])

        for item in resolved_items:
            PackageCapacityRepository.check_and_raise_subscription(
                db=db,
                vendor_id=payload.vendor_id,
                package_id=item["package_id"],
                package_name=item["package_name"],
                requested_qty=item["quantity"],
                individual_slots=individual_slots,
            )

        # 7. Calculate amounts
        # meal_slot_multiplier accounts for how many meals per day the plan covers
        meal_slot_multiplier = MEAL_SLOT_MULTIPLIER.get(plan.meal_slot, 1)

        daily_total = sum(
            i["unit_price"] * i["quantity"]
            for i in resolved_items
        )

        total_amount = daily_total * meal_slot_multiplier * plan.duration_days

        discount_amount = (
            total_amount * Decimal(str(plan.discount_percent)) / 100
        ).quantize(Decimal("0.01"))

        final_amount = total_amount - discount_amount

        # 8. Check wallet balance
        wallet = WalletRepository.get_by_user_id(db, user_id)

        if not wallet:

            raise HTTPException(
                status_code=400,
                detail="Wallet not found. Please recharge your wallet first."
            )

        if Decimal(str(wallet.balance)) < final_amount:

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Insufficient wallet balance. "
                    f"Required: {final_amount}, "
                    f"Available: {wallet.balance}"
                )
            )

        # 9. Atomic: create subscription + packages (wallet deducted per order, not here)
        try:

            end_date = payload.start_date + timedelta(
                days=plan.duration_days
            )

            subscription_data = {
                "user_reference_id": user_id,
                "vendor_reference_id": str(payload.vendor_id),
                "plan_reference_id": str(payload.plan_id),
                "user_address_reference_id": str(payload.address_id),
                "status": "active",
                "meal_slot": plan.meal_slot,
                "subscription_type": plan.subscription_type,
                "start_date": payload.start_date,
                "end_date": end_date,
                "free_skips_total": plan.free_skips,
                "free_skips_used": 0,
                "total_amount": total_amount,
                "discount_amount": discount_amount,
                "final_amount": final_amount
            }

            subscription = SubscriptionRepository.create(
                db, subscription_data
            )

            for item in resolved_items:

                SubscriptionRepository.create_package(
                    db,
                    {
                        "subscription_reference_id": subscription.subscription_id,
                        "package_reference_id": str(item["package_id"]),
                        "quantity": item["quantity"],
                        "unit_price": item["unit_price"]
                    }
                )

            # Deduct full subscription amount from wallet upfront
            balance_before = Decimal(str(wallet.balance))
            WalletRepository.deduct_balance(db, wallet, final_amount)
            balance_after = Decimal(str(wallet.balance))

            WalletRepository.create_transaction(
                db,
                {
                    "wallet_reference_id": str(wallet.wallet_id),
                    "user_reference_id": user_id,
                    "type": "debit",
                    "reason": "subscription_payment",
                    "amount": final_amount,
                    "balance_before": balance_before,
                    "balance_after": balance_after,
                    "reference_id": subscription.subscription_id,
                    "reference_type": "subscription",
                    "description": (
                        f"Subscription payment — "
                        f"{plan.meal_slot} {plan.subscription_type} "
                        f"({plan.duration_days} days)"
                    ),
                }
            )

            # Remove subscribed packages from cart
            subscribed_package_ids = [str(i["package_id"]) for i in resolved_items]
            CartRepository.delete_by_package_ids(db, user_id, subscribed_package_ids)

            db.commit()

            db.refresh(subscription)

            return {
                "success": True,
                "message": "Subscription created successfully",
                "subscription_id": subscription.subscription_id,
                "total_amount": total_amount,
                "discount_amount": discount_amount,
                "final_amount": final_amount,
                "wallet_balance_after": balance_after,
            }

        except HTTPException:

            db.rollback()

            raise

        except Exception as e:

            db.rollback()

            raise HTTPException(
                status_code=500,
                detail=f"Subscription failed: {str(e)}"
            )

    @staticmethod
    def get_my_subscriptions(
        db: Session,
        user_id: str
    ):

        subscriptions = SubscriptionRepository.get_all_by_user(
            db, user_id
        )

        return {
            "success": True,
            "total": len(subscriptions),
            "subscriptions": subscriptions
        }

    @staticmethod
    def get_subscription(
        db: Session,
        user_id: str,
        subscription_id
    ):

        subscription = SubscriptionRepository.get_by_id(
            db, subscription_id
        )

        if not subscription:

            raise HTTPException(
                status_code=404,
                detail="Subscription not found"
            )

        if str(subscription.user_reference_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        return subscription

    @staticmethod
    def _get_owned_subscription(
        db: Session,
        user_id: str,
        subscription_id
    ):
        """Load a subscription and verify it belongs to the caller."""

        subscription = SubscriptionRepository.get_by_id(
            db, subscription_id
        )

        if not subscription:

            raise HTTPException(
                status_code=404,
                detail="Subscription not found"
            )

        if str(subscription.user_reference_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        return subscription

    @staticmethod
    def list_subscription_orders(
        db: Session,
        user_id: str,
        subscription_id,
        status: str = None,
        order_date: date = None
    ):

        subscription = SubscriptionService._get_owned_subscription(
            db, user_id, subscription_id
        )

        orders = SubscriptionRepository.get_orders_by_subscription(
            db,
            subscription.subscription_id,
            status=status,
            order_date=order_date
        )

        status_summary = {}

        for order in orders:

            status_summary[order.status] = status_summary.get(order.status, 0) + 1

        return {
            "success": True,
            "subscription_id": subscription.subscription_id,
            "subscription_status": subscription.status,
            "total": len(orders),
            "status_summary": status_summary,
            "orders": orders
        }

    @staticmethod
    def get_subscription_order(
        db: Session,
        user_id: str,
        subscription_id,
        order_id
    ):

        subscription = SubscriptionService._get_owned_subscription(
            db, user_id, subscription_id
        )

        row = SubscriptionRepository.get_order_detail_by_id_and_subscription(
            db, order_id, subscription.subscription_id
        )

        if not row:

            raise HTTPException(
                status_code=404,
                detail="Order not found"
            )

        order, address, vendor, delivery_boy = row

        packages = []

        for sub_pkg, pkg in SubscriptionRepository.get_packages_with_menu_by_subscription(
            db, subscription.subscription_id
        ):

            primary_image = None

            for img in pkg.images:

                if img.is_primary:

                    primary_image = img.image_url

                    break

            packages.append({
                "package_id": pkg.package_id,
                "package_name": pkg.package_name,
                "meal_type": pkg.meal_type,
                "food_type": pkg.food_type,
                "quantity": sub_pkg.quantity,
                "unit_price": sub_pkg.unit_price,
                "primary_image": primary_image
            })

        return {
            "success": True,
            "order": order,
            "delivery_address": address,
            "packages": packages,
            "vendor": vendor,
            "delivery_boy": delivery_boy
        }

    @staticmethod
    def _per_meal_amount(subscription) -> Decimal:
        """
        What the customer effectively paid for one meal order:
        final_amount spread over every serviceable day × meals per day.
        Paused days extend end_date, so they are excluded from the day count.
        """

        service_days = (
            (subscription.end_date - subscription.start_date).days
            - (subscription.total_days_paused or 0)
        )

        meals_per_day = len(
            MEAL_SLOT_EXPANSION.get(subscription.meal_slot, [subscription.meal_slot])
        )

        total_meals = max(service_days * meals_per_day, 1)

        return (
            Decimal(str(subscription.final_amount)) / total_meals
        ).quantize(Decimal("0.01"))

    @staticmethod
    def skip_order(
        db: Session,
        user_id: str,
        subscription_id,
        order_id
    ):

        subscription = SubscriptionService._get_owned_subscription(
            db, user_id, subscription_id
        )

        if subscription.status != "active":

            raise HTTPException(
                status_code=400,
                detail=f"Cannot skip orders of a subscription that is {subscription.status}"
            )

        order = SubscriptionRepository.get_order_by_id_and_subscription(
            db, order_id, subscription.subscription_id
        )

        if not order:

            raise HTTPException(
                status_code=404,
                detail="Order not found"
            )

        if order.status != "scheduled":

            raise HTTPException(
                status_code=400,
                detail=f"Only scheduled orders can be skipped. This order is {order.status}"
            )

        now_local = datetime.now()

        if order.order_date < now_local.date():

            raise HTTPException(
                status_code=400,
                detail="Past orders cannot be skipped"
            )

        cutoff_time = FREE_SKIP_CUTOFF.get(order.meal_slot)

        if cutoff_time is None:

            raise HTTPException(
                status_code=400,
                detail=f"Unsupported meal slot '{order.meal_slot}'"
            )

        # Cutoff is on the order date itself; for a future date the request is
        # always before it, so only same-day skips can miss the window.
        skip_deadline_local = datetime.combine(order.order_date, cutoff_time)
        skip_deadline = skip_deadline_local.astimezone()

        before_cutoff = now_local < skip_deadline_local

        free_skips_total = subscription.free_skips_total or 0
        free_skips_used = subscription.free_skips_used or 0
        free_skips_remaining = free_skips_total - free_skips_used

        not_free_reason = None

        if not before_cutoff:
            not_free_reason = "cutoff_passed"

        elif free_skips_remaining <= 0:
            not_free_reason = "no_free_skips_left"

        is_free_skip = not_free_reason is None

        refund_amount = Decimal("0.00")
        wallet_balance_after = None

        try:

            SubscriptionRepository.skip_order(
                db,
                order,
                is_free_skip=is_free_skip,
                skip_requested_at=datetime.now(timezone.utc),
                skip_deadline=skip_deadline
            )

            if is_free_skip:

                SubscriptionRepository.consume_free_skip(db, subscription)
                free_skips_used += 1
                free_skips_remaining -= 1

                refund_amount = SubscriptionService._per_meal_amount(subscription)

                if refund_amount > 0:

                    wallet = WalletRepository.get_or_create(db, user_id)

                    balance_before = Decimal(str(wallet.balance))
                    WalletRepository.credit_balance(db, wallet, refund_amount)
                    wallet_balance_after = Decimal(str(wallet.balance))

                    WalletRepository.create_transaction(
                        db,
                        {
                            "wallet_reference_id": str(wallet.wallet_id),
                            "user_reference_id": user_id,
                            "type": "credit",
                            "reason": "free_skip_refund",
                            "amount": refund_amount,
                            "balance_before": balance_before,
                            "balance_after": wallet_balance_after,
                            "reference_id": order.order_id,
                            "reference_type": "order",
                            "description": (
                                f"Free skip refund — {order.meal_slot} on {order.order_date}"
                            ),
                        }
                    )

            db.commit()

        except HTTPException:

            db.rollback()

            raise

        except Exception as e:

            db.rollback()

            raise HTTPException(
                status_code=500,
                detail=f"Skip failed: {str(e)}"
            )

        # Let the assigned delivery partner know; must never fail the completed skip
        if order.delivery_boy_reference_id:

            try:

                DeliveryBoyRepository.create_notification(
                    db,
                    delivery_boy_id=order.delivery_boy_reference_id,
                    type="schedule_update",
                    title="Delivery skipped by customer",
                    body=(
                        f"The {order.meal_slot} delivery on {order.order_date} "
                        f"was skipped by the customer."
                    ),
                    data={"order_id": str(order.order_id), "order_date": str(order.order_date)},
                )

                db.commit()

            except Exception:

                db.rollback()

        cutoff_label = cutoff_time.strftime("%I:%M %p").lstrip("0")

        if is_free_skip:
            message = f"Order skipped. ₹{refund_amount} refunded to your wallet as a free skip"
        elif not_free_reason == "cutoff_passed":
            message = (
                f"Order skipped. The free-skip cutoff for {order.meal_slot} "
                f"({cutoff_label}) has passed, so no refund was issued"
            )
        else:
            message = "Order skipped. No free skips left on this subscription, so no refund was issued"

        return {
            "success": True,
            "message": message,
            "order_id": order.order_id,
            "status": order.status,
            "is_free_skip": is_free_skip,
            "not_free_reason": not_free_reason,
            "skip_deadline": skip_deadline,
            "refund_amount": refund_amount,
            "wallet_balance_after": wallet_balance_after,
            "free_skips_total": free_skips_total,
            "free_skips_used": free_skips_used,
            "free_skips_remaining": free_skips_remaining,
        }

    @staticmethod
    def cancel_subscription(
        db: Session,
        user_id: str,
        subscription_id,
        payload
    ):

        subscription = SubscriptionRepository.get_by_id(
            db, subscription_id
        )

        if not subscription:

            raise HTTPException(
                status_code=404,
                detail="Subscription not found"
            )

        if str(subscription.user_reference_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        if subscription.status != "active":

            raise HTTPException(
                status_code=400,
                detail=f"Subscription is already {subscription.status}"
            )

        SubscriptionRepository.cancel(
            db,
            subscription,
            payload.cancel_reason or "Cancelled by user"
        )

        db.commit()

        db.refresh(subscription)

        return {
            "success": True,
            "message": "Subscription cancelled successfully"
        }

    @staticmethod
    def pause_subscription(
        db: Session,
        user_id: str,
        subscription_id
    ):
        subscription = SubscriptionRepository.get_by_id(db, subscription_id)

        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        if str(subscription.user_reference_id) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        if subscription.status != "active":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot pause a subscription that is {subscription.status}"
            )

        pause_start_date = date.today() + timedelta(days=1)

        if pause_start_date >= subscription.end_date:
            raise HTTPException(
                status_code=400,
                detail="Subscription ends before the pause would take effect"
            )

        try:
            # Cancel all future scheduled orders from the pause date onwards
            db.query(Order).filter(
                Order.subscription_reference_id == subscription.subscription_id,
                Order.order_date >= pause_start_date,
                Order.status == "scheduled"
            ).update({"status": "cancelled"}, synchronize_session=False)

            SubscriptionRepository.pause(db, subscription, pause_start_date)

            db.commit()

            return {
                "success": True,
                "message": "Subscription paused successfully",
                "pause_start_date": str(pause_start_date)
            }

        except HTTPException:
            db.rollback()
            raise

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Pause failed: {str(e)}")

    @staticmethod
    def resume_subscription(
        db: Session,
        user_id: str,
        subscription_id
    ):
        subscription = SubscriptionRepository.get_by_id(db, subscription_id)

        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        if str(subscription.user_reference_id) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        if subscription.status != "paused":
            raise HTTPException(
                status_code=400,
                detail="Only a paused subscription can be resumed"
            )

        resume_date = date.today() + timedelta(days=1)
        days_paused = (resume_date - subscription.pause_start_date).days
        old_end_date = subscription.end_date
        new_end_date = old_end_date + timedelta(days=days_paused)

        try:
            # Reactivate cancelled orders that fall within the resumed window
            # (resume_date up to but not including old_end_date)
            db.query(Order).filter(
                Order.subscription_reference_id == subscription.subscription_id,
                Order.order_date >= resume_date,
                Order.order_date < old_end_date,
                Order.status == "cancelled"
            ).update({"status": "scheduled"}, synchronize_session=False)

            # Create new orders for the extension period (old_end_date → new_end_date)
            individual_slots = MEAL_SLOT_EXPANSION.get(
                subscription.meal_slot, [subscription.meal_slot]
            )

            new_orders = []
            current_date = old_end_date

            while current_date < new_end_date:
                for slot in individual_slots:
                    new_orders.append({
                        "order_id": uuid.uuid4(),
                        "subscription_reference_id": subscription.subscription_id,
                        "user_reference_id": subscription.user_reference_id,
                        "vendor_reference_id": subscription.vendor_reference_id,
                        "delivery_address_reference_id": subscription.user_address_reference_id,
                        "order_date": current_date,
                        "meal_slot": slot,
                        "status": "scheduled",
                        "is_free_skip": False,
                        "otp_for_delivery": str(random.randint(100000, 999999)),
                    })
                current_date += timedelta(days=1)

            if new_orders:
                db.bulk_insert_mappings(Order, new_orders)

            SubscriptionRepository.resume(db, subscription, days_paused, new_end_date)

            db.commit()

            return {
                "success": True,
                "message": "Subscription resumed successfully",
                "resume_date": str(resume_date),
                "new_end_date": str(new_end_date),
                "days_paused": days_paused,
                "new_orders_created": len(new_orders)
            }

        except HTTPException:
            db.rollback()
            raise

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Resume failed: {str(e)}")
