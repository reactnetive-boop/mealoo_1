"""
Capacity-related queries for provider packages.

daily_capacity on ProviderSelectedPackage represents the maximum units of a
package a provider can serve per individual meal-slot per day.
NULL means no limit is enforced.
"""
from datetime import date as date_type

from sqlalchemy import func
from sqlalchemy.orm import Session

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
