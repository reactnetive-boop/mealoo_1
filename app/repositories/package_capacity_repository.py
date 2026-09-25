"""
Capacity-related queries for provider packages.

Two independent limits are enforced, and an order must fit inside both:

1. daily_capacity on ProviderSelectedPackage - the maximum units of a single
   package a provider can serve per individual meal-slot per day.
2. daily_meal_quota on Provider - the maximum meals the provider can serve per
   individual meal-slot per day across ALL of that provider's packages
   (e.g. quota 15 = 15 breakfasts + 15 lunches + 15 dinners per day, whatever
   mix of packages they come from).

NULL means no limit is enforced, for either one.
"""
from datetime import date as date_type

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.provider_model import Provider
from app.models.provider_selected_package_model import ProviderSelectedPackage
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.extra_order_model import ExtraOrder


# Which subscription meal_slot values cover each individual slot
_SLOT_COVERING_GROUPS: dict[str, list[str]] = {
    "breakfast": ["breakfast", "breakfast_lunch", "breakfast_dinner", "all_slots"],
    "lunch":     ["lunch",     "breakfast_lunch", "lunch_dinner",     "all_slots"],
    "dinner":    ["dinner",    "breakfast_dinner", "lunch_dinner",    "all_slots"],
}


class PackageCapacityRepository:

    @staticmethod
    def get_capacity(
        db: Session,
        vendor_id,
        package_id
    ) -> int | None:
        """
        Return the daily_capacity for a provider-package pair.
        Returns None if the record doesn't exist or no limit is set.
        """
        row = (
            db.query(ProviderSelectedPackage.daily_capacity)
            .filter(
                ProviderSelectedPackage.provider_id == vendor_id,
                ProviderSelectedPackage.package_id == package_id,
                ProviderSelectedPackage.is_active == True,
            )
            .first()
        )
        if row is None or row.daily_capacity is None:
            return None
        return int(row.daily_capacity)

    @staticmethod
    def get_subscription_demand_per_slot(
        db: Session,
        vendor_id,
        package_id,
        individual_slot: str,
    ) -> int:
        """
        Sum of quantities committed by all active subscriptions for this
        vendor + package combination on the given individual meal-slot.

        Counts all subscription meal-slot variants that include this slot
        (e.g. 'all_slots' counts towards 'breakfast', 'lunch', and 'dinner').
        """
        covering = _SLOT_COVERING_GROUPS.get(individual_slot, [individual_slot])

        total = (
            db.query(func.coalesce(func.sum(SubscriptionPackage.quantity), 0))
            .join(Subscription, SubscriptionPackage.subscription_reference_id == Subscription.subscription_id)
            .filter(
                Subscription.vendor_reference_id == vendor_id,
                SubscriptionPackage.package_reference_id == package_id,
                Subscription.status == "active",
                Subscription.meal_slot.in_(covering),
            )
            .scalar()
        )
        return int(total or 0)

    @staticmethod
    def get_extra_order_demand(
        db: Session,
        vendor_id,
        package_id,
        delivery_date: date_type,
        meal_slot: str,
    ) -> int:
        """
        Sum of quantities from non-cancelled extra orders for this vendor +
        package on a specific date and meal-slot.
        """
        total = (
            db.query(func.coalesce(func.sum(ExtraOrder.quantity), 0))
            .filter(
                ExtraOrder.vendor_reference_id == vendor_id,
                ExtraOrder.package_reference_id == package_id,
                ExtraOrder.delivery_date == delivery_date,
                ExtraOrder.meal_slot == meal_slot,
                ExtraOrder.status != "cancelled",
            )
            .scalar()
        )
        return int(total or 0)

    @staticmethod
    def check_and_raise_subscription(
        db: Session,
        vendor_id,
        package_id,
        package_name: str,
        requested_qty: int,
        individual_slots: list[str],
    ) -> None:
        """
        Raise HTTPException 400 if adding `requested_qty` of `package_id`
        would exceed the provider's daily capacity on any of the given slots.
        No-op when no capacity limit is set.
        """
        from fastapi import HTTPException

        capacity = PackageCapacityRepository.get_capacity(db, vendor_id, package_id)
        if capacity is None:
            return

        for slot in individual_slots:
            current = PackageCapacityRepository.get_subscription_demand_per_slot(
                db, vendor_id, package_id, slot
            )
            if current + requested_qty > capacity:
                available = max(0, capacity - current)
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Package '{package_name}' has reached its daily capacity "
                        f"for {slot}. "
                        f"Provider limit: {capacity}, "
                        f"already committed: {current}, "
                        f"requested: {requested_qty}, "
                        f"available: {available}."
                    ),
                )

    @staticmethod
    def check_and_raise_extra_order(
        db: Session,
        vendor_id,
        package_id,
        package_name: str,
        requested_qty: int,
        delivery_date: date_type,
        meal_slot: str,
    ) -> None:
        """
        Raise HTTPException 400 if adding `requested_qty` for an extra order
        would exceed the provider's daily capacity.
        No-op when no capacity limit is set.
        """
        from fastapi import HTTPException

        capacity = PackageCapacityRepository.get_capacity(db, vendor_id, package_id)
        if capacity is None:
            return

        sub_demand = PackageCapacityRepository.get_subscription_demand_per_slot(
            db, vendor_id, package_id, meal_slot
        )
        extra_demand = PackageCapacityRepository.get_extra_order_demand(
            db, vendor_id, package_id, delivery_date, meal_slot
        )

        total = sub_demand + extra_demand
        if total + requested_qty > capacity:
            available = max(0, capacity - total)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Package '{package_name}' has reached its daily capacity "
                    f"for {meal_slot} on {delivery_date}. "
                    f"Provider limit: {capacity}, "
                    f"already committed: {total}, "
                    f"requested: {requested_qty}, "
                    f"available: {available}."
                ),
            )

    # ── Provider-level daily quota (all packages together) ──

    @staticmethod
    def _get_provider_row(db: Session, vendor_id):
        return (
            db.query(Provider.business_name, Provider.daily_meal_quota)
            .filter(Provider.provider_id == vendor_id)
            .first()
        )

    @staticmethod
    def get_provider_quota(
        db: Session,
        vendor_id
    ) -> int | None:
        """
        Return the provider's daily_meal_quota.
        Returns None if the provider doesn't exist or no limit is set.
        """
        row = PackageCapacityRepository._get_provider_row(db, vendor_id)
        if row is None or row.daily_meal_quota is None:
            return None
        return int(row.daily_meal_quota)

    @staticmethod
    def get_provider_subscription_demand_per_slot(
        db: Session,
        vendor_id,
        individual_slot: str,
    ) -> int:
        """
        Sum of quantities committed by all active subscriptions for this
        vendor on the given individual meal-slot, across every package.
        """
        covering = _SLOT_COVERING_GROUPS.get(individual_slot, [individual_slot])

        total = (
            db.query(func.coalesce(func.sum(SubscriptionPackage.quantity), 0))
            .join(Subscription, SubscriptionPackage.subscription_reference_id == Subscription.subscription_id)
            .filter(
                Subscription.vendor_reference_id == vendor_id,
                Subscription.status == "active",
                Subscription.meal_slot.in_(covering),
            )
            .scalar()
        )
        return int(total or 0)

    @staticmethod
    def get_provider_extra_order_demand(
        db: Session,
        vendor_id,
        delivery_date: date_type,
        meal_slot: str,
    ) -> int:
        """
        Sum of quantities from non-cancelled extra orders for this vendor on a
        specific date and meal-slot, across every package.
        """
        total = (
            db.query(func.coalesce(func.sum(ExtraOrder.quantity), 0))
            .filter(
                ExtraOrder.vendor_reference_id == vendor_id,
                ExtraOrder.delivery_date == delivery_date,
                ExtraOrder.meal_slot == meal_slot,
                ExtraOrder.status != "cancelled",
            )
            .scalar()
        )
        return int(total or 0)

    @staticmethod
    def check_and_raise_provider_subscription(
        db: Session,
        vendor_id,
        requested_qty: int,
        individual_slots: list[str],
    ) -> None:
        """
        Raise HTTPException 400 if `requested_qty` more meals would push the
        provider past its daily_meal_quota on any of the given slots.
        No-op when the provider has no quota set.
        """
        from fastapi import HTTPException

        row = PackageCapacityRepository._get_provider_row(db, vendor_id)
        if row is None or row.daily_meal_quota is None:
            return

        quota = int(row.daily_meal_quota)
        name = row.business_name or "This provider"

        for slot in individual_slots:
            current = PackageCapacityRepository.get_provider_subscription_demand_per_slot(
                db, vendor_id, slot
            )
            if current + requested_qty > quota:
                available = max(0, quota - current)
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{name} has reached its daily limit for {slot}. "
                        f"Daily limit: {quota} meal(s) across all packages, "
                        f"already committed: {current}, "
                        f"requested: {requested_qty}, "
                        f"available: {available}."
                    ),
                )

    @staticmethod
    def check_and_raise_provider_extra_order(
        db: Session,
        vendor_id,
        requested_qty: int,
        delivery_date: date_type,
        meal_slot: str,
    ) -> None:
        """
        Raise HTTPException 400 if `requested_qty` more meals would push the
        provider past its daily_meal_quota for that date and slot.
        Counts active subscriptions plus extra orders already placed.
        No-op when the provider has no quota set.
        """
        from fastapi import HTTPException

        row = PackageCapacityRepository._get_provider_row(db, vendor_id)
        if row is None or row.daily_meal_quota is None:
            return

        quota = int(row.daily_meal_quota)
        name = row.business_name or "This provider"

        sub_demand = PackageCapacityRepository.get_provider_subscription_demand_per_slot(
            db, vendor_id, meal_slot
        )
        extra_demand = PackageCapacityRepository.get_provider_extra_order_demand(
            db, vendor_id, delivery_date, meal_slot
        )

        total = sub_demand + extra_demand
        if total + requested_qty > quota:
            available = max(0, quota - total)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{name} has reached its daily limit for {meal_slot} "
                    f"on {delivery_date}. "
                    f"Daily limit: {quota} meal(s) across all packages, "
                    f"already committed: {total}, "
                    f"requested: {requested_qty}, "
                    f"available: {available}."
                ),
            )

    @staticmethod
    def get_provider_quota_status(
        db: Session,
        vendor_id,
        for_date: date_type,
    ) -> dict:
        """
        Per-slot picture of how much of the provider's daily quota is used on
        `for_date`: active subscription commitments plus extra orders.
        `available` / `is_full` are None / False when no quota is set.
        """
        row = PackageCapacityRepository._get_provider_row(db, vendor_id)
        quota = (
            int(row.daily_meal_quota)
            if row is not None and row.daily_meal_quota is not None
            else None
        )

        slots = {}
        for slot in ("breakfast", "lunch", "dinner"):
            sub_demand = PackageCapacityRepository.get_provider_subscription_demand_per_slot(
                db, vendor_id, slot
            )
            extra_demand = PackageCapacityRepository.get_provider_extra_order_demand(
                db, vendor_id, for_date, slot
            )
            committed = sub_demand + extra_demand
            slots[slot] = {
                "subscription_committed": sub_demand,
                "extra_orders": extra_demand,
                "total_committed": committed,
                "available": max(0, quota - committed) if quota is not None else None,
                "is_full": quota is not None and committed >= quota,
            }

        return {
            "daily_meal_quota": quota,
            "date": for_date,
            "slots": slots,
        }

    @staticmethod
    def validate_provider_quota_reduction(
        db: Session,
        vendor_id,
        new_quota: int,
    ) -> int:
        """
        Return the peak active-subscription demand across all individual slots
        for this provider. Raises HTTPException 400 if new_quota is below it,
        so a quota change can never strand meals already committed.
        """
        from fastapi import HTTPException

        peak = 0
        for slot in ("breakfast", "lunch", "dinner"):
            demand = PackageCapacityRepository.get_provider_subscription_demand_per_slot(
                db, vendor_id, slot
            )
            if demand > peak:
                peak = demand

        if new_quota < peak:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot set the daily limit to {new_quota}: "
                    f"current peak subscription demand is {peak} meal(s) per slot. "
                    f"The limit must be at least {peak}."
                ),
            )
        return peak

    @staticmethod
    def validate_capacity_reduction(
        db: Session,
        vendor_id,
        package_id,
        new_capacity: int,
    ) -> int:
        """
        Return the peak current demand across all individual slots.
        Raises HTTPException 400 if new_capacity is less than the peak demand.
        """
        from fastapi import HTTPException

        peak = 0
        for slot in ("breakfast", "lunch", "dinner"):
            demand = PackageCapacityRepository.get_subscription_demand_per_slot(
                db, vendor_id, package_id, slot
            )
            if demand > peak:
                peak = demand

        if new_capacity < peak:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot set capacity to {new_capacity}: "
                    f"current peak subscription demand is {peak}. "
                    f"Capacity must be at least {peak}."
                ),
            )
        return peak
