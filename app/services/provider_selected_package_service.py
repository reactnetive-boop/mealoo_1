from fastapi import HTTPException

from app.repositories.menu_repository import (
    MenuRepository
)

from app.repositories.provider_selected_package_repository import (
    ProviderSelectedPackageRepository
)


class ProviderSelectedPackageService:

    @staticmethod
    def select_package(
        db,
        request
    ):

        package = (
            MenuRepository
            .get_package_by_id(
                db=db,
                package_id=request.package_id
            )
        )

        if not package:
            raise HTTPException(
                status_code=404,
                detail="Package not found"
            )

        existing = (
            ProviderSelectedPackageRepository
            .get_provider_package(
                db=db,
                provider_id=request.provider_id,
                package_id=request.package_id
            )
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Package already selected"
            )

        ProviderSelectedPackageRepository.create(
            db=db,
            provider_id=request.provider_id,
            package_id=request.package_id
        )

        return {
            "success": True,
            "message": "Package selected successfully"
        }