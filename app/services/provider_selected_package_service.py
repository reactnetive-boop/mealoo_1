from fastapi import HTTPException

from app.repositories.menu_repository import MenuRepository
from app.repositories.provider_selected_package_repository import ProviderSelectedPackageRepository
from app.repositories.package_capacity_repository import PackageCapacityRepository


class ProviderSelectedPackageService:

    @staticmethod
    def select_package(db, request):

        package = MenuRepository.get_package_by_id(
            db=db,
            package_id=request.package_id
        )

        if not package:
            raise HTTPException(status_code=404, detail="Package not found")

        # A provider may select a catalogue package only while it is live; their
        # own draft is attached automatically at creation time.
        if not package.is_active and str(package.provider_id) != str(request.provider_id):
            raise HTTPException(
                status_code=400,
                detail="Package is not active and cannot be selected"
            )

        existing = ProviderSelectedPackageRepository.get_provider_package(
            db=db,
            provider_id=request.provider_id,
            package_id=request.package_id
        )

        if existing:
            raise HTTPException(status_code=400, detail="Package already selected")

        # If a capacity is specified, validate it isn't below current demand
        # (no existing demand since it's a new selection, but guard just in case)
        daily_capacity = getattr(request, "daily_capacity", None)

        if daily_capacity is not None:
            PackageCapacityRepository.validate_capacity_reduction(
                db, request.provider_id, request.package_id, daily_capacity
            )

        record = ProviderSelectedPackageRepository.create(
            db=db,
            provider_id=request.provider_id,
            package_id=request.package_id,
            daily_capacity=daily_capacity,
        )

        return {
            "success": True,
            "message": "Package selected successfully",
            "daily_capacity": record.daily_capacity,
        }

    @staticmethod
    def get_capacity(db, provider_id, package_id):
        """
        Current daily capacity for a provider-package pair, plus the peak
        per-slot demand from active subscriptions (the lowest allowed limit).
        """
        existing = ProviderSelectedPackageRepository.get_provider_package(
            db=db,
            provider_id=provider_id,
            package_id=package_id
        )

        if not existing:
            raise HTTPException(
                status_code=404,
                detail="Provider-package assignment not found"
            )

        return {
            "success": True,
            "message": "Capacity fetched successfully",
            "daily_capacity": existing.daily_capacity,
            "current_peak_demand": PackageCapacityRepository.get_peak_subscription_demand(
                db, provider_id, package_id
            ),
        }

    @staticmethod
    def update_capacity(db, request):
        """
        Set or clear the daily capacity for an existing provider-package pair.
        Rejects the update if the new limit is below current peak demand.
        """
        existing = ProviderSelectedPackageRepository.get_provider_package(
            db=db,
            provider_id=request.provider_id,
            package_id=request.package_id
        )

        if not existing:
            raise HTTPException(
                status_code=404,
                detail="Provider-package assignment not found"
            )

        new_capacity = request.daily_capacity
        peak_demand = 0

        if new_capacity is not None:
            # Validate the new limit doesn't undercut existing subscriptions
            peak_demand = PackageCapacityRepository.validate_capacity_reduction(
                db, request.provider_id, request.package_id, new_capacity
            )

        record = ProviderSelectedPackageRepository.update_capacity(
            db=db,
            provider_id=request.provider_id,
            package_id=request.package_id,
            daily_capacity=new_capacity,
        )

        return {
            "success": True,
            "message": (
                f"Capacity updated to {new_capacity}"
                if new_capacity is not None
                else "Capacity limit removed"
            ),
            "daily_capacity": record.daily_capacity,
            "current_peak_demand": peak_demand,
        }