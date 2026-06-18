from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.menu_repository import MenuRepository
from app.repositories.user_address_repository import UserAddressRepository
from app.repositories.wallet_repository import WalletRepository


MEAL_SLOT_MULTIPLIER = {
    "breakfast": 1,
    "lunch": 1,
    "dinner": 1,
    "breakfast_lunch": 2,
    "lunch_dinner": 2,
    "breakfast_dinner": 2,
    "all_slots": 3,
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
                "subscription_id": str(sub.id),
                "subscription_status": sub.status,
                "meal_slot": sub.meal_slot,
                "start_date": str(sub.start_date),
                "end_date": str(sub.end_date),
                "package_id": str(pkg.package_id),
                "category_id": str(pkg.category_id),
                "provider_id": str(sub.vendor_id),
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
        # 1. Check user has no active subscription already
        existing = SubscriptionRepository.get_active_by_user(
            db, user_id
        )

        if existing:

            raise HTTPException(
                status_code=400,
                detail=(
                    "You already have an active subscription. "
                    "Please cancel it before subscribing to a new one."
                )
            )

        # 2. Validate plan
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

        if not address or str(address.user_id) != user_id:

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
                "unit_price": effective_price,
                "quantity": item.quantity
            })

        # 5. Calculate amounts
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

        # 6. Check wallet balance
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

        # 7. Atomic: create subscription + packages + deduct wallet + payment
        try:

            end_date = payload.start_date + timedelta(
                days=plan.duration_days
            )

            subscription_data = {
                "user_id": user_id,
                "vendor_id": str(payload.vendor_id),
                "plan_id": str(payload.plan_id),
                "user_address_id": str(payload.address_id),
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
                        "subscription_id": subscription.id,
                        "package_id": str(item["package_id"]),
                        "quantity": item["quantity"],
                        "unit_price": item["unit_price"]
                    }
                )

            balance_before = Decimal(str(wallet.balance))

            WalletRepository.deduct_balance(
                db, wallet, final_amount
            )

            balance_after = Decimal(str(wallet.balance))

            WalletRepository.create_transaction(
                db,
                {
                    "wallet_id": wallet.id,
                    "user_id": user_id,
                    "type": "debit",
                    "reason": "subscription",
                    "amount": final_amount,
                    "balance_before": balance_before,
                    "balance_after": balance_after,
                    "reference_id": subscription.id,
                    "reference_type": "subscription",
                    "description": (
                        f"{plan.subscription_type.capitalize()} "
                        f"subscription payment"
                    ),
                    "created_by": user_id
                }
            )

            PaymentRepository.create(
                db,
                {
                    "subscription_id": subscription.id,
                    "user_id": user_id,
                    "amount": final_amount,
                    "currency": "INR",
                    "method": "wallet",
                    "status": "completed"
                }
            )

            db.commit()

            db.refresh(subscription)

            return {
                "success": True,
                "message": "Subscription created successfully",
                "subscription_id": subscription.id,
                "total_amount": total_amount,
                "discount_amount": discount_amount,
                "final_amount": final_amount,
                "wallet_balance_after": balance_after
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

        if str(subscription.user_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        return subscription

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

        if str(subscription.user_id) != user_id:

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
