from fastapi import HTTPException

from app.repositories.provider_repository import (
    ProviderRepository
)

from fastapi import UploadFile

from sqlalchemy.orm import Session

from app.utils.file_helper import (
    save_profile_image
)
from app.services.pincode_service import PincodeService
from app.repositories.package_capacity_repository import (
    PackageCapacityRepository
)

from datetime import date as date_type

class ProviderService:


    @staticmethod
    def complete_profile(
        db,
        provider_id: str,
        payload
    ):

        provider = (
            ProviderRepository.get_by_provider_id(
                db,
                provider_id
            )
        )

        if not provider:

            raise HTTPException(
                status_code=404,
                detail="Provider not found"
            )

        update_data = payload.model_dump(
            exclude_unset=True
        )

        update_data[
            "is_profile_completed"
        ] = True

        updated_provider = (
            ProviderRepository.update_provider(
                db,
                provider,
                update_data
            )
        )

        return {

            "success": True,

            "message": (
                "Profile completed successfully"
            ),

            "provider_id": (
                updated_provider.provider_id
            ),

            "is_profile_completed": (
                updated_provider.is_profile_completed
            )
        }


    @staticmethod
    def get_profile(
        db,
        provider_id: str
    ):

        provider = (
            ProviderRepository.get_by_provider_id(
                db,
                provider_id
            )
        )

        if not provider:

            raise HTTPException(
                status_code=404,
                detail="Provider not found"
            )

        return provider
    
    @staticmethod
    def update_profile_image(
        db: Session,
        provider_id: str,
        file: UploadFile
    ):

        provider = (
            ProviderRepository.get_by_provider_id(
                db,
                provider_id
            )
        )

        if not provider:

            return {
                "success": False,
                "message": (
                    "Provider not found"
                ),
                "profile_image": (
                    ""
                )
            }


        allowed_extensions = [
            "jpg",
            "jpeg",
            "png",
            "webp"
        ]

        file_extension = (
            file.filename.split(".")[-1].lower()
        )

        if file_extension not in allowed_extensions:

            return {
                "success": False,
                "message": (
                    "Invalid image format! Image should have jpg, jpeg, png and webp."
                ),
                "profile_image": (
                    ""
                )
            }

        image_path = (
            save_profile_image(file)
        )

        updated_provider = (
            ProviderRepository.update_profile_image(
                db,
                provider,
                image_path
            )
        )

        return {
            "success": True,
            "message": (
                "Profile image updated successfully"
            ),
            "profile_image": (
                updated_provider.profile_image
            )
        }
        
    @staticmethod
    def update_daily_quota(
        db,
        provider_id: str,
        payload
    ):

        provider = (
            ProviderRepository.get_by_provider_id(
                db,
                provider_id
            )
        )

        if not provider:

            raise HTTPException(
                status_code=404,
                detail="Provider not found"
            )

        new_quota = payload.daily_meal_quota
        peak_demand = 0

        if new_quota is not None:

            # a new limit can never sit below meals already committed
            peak_demand = (
                PackageCapacityRepository.validate_provider_quota_reduction(
                    db,
                    provider_id,
                    new_quota
                )
            )

        provider.daily_meal_quota = new_quota

        db.commit()
        db.refresh(provider)

        return {
            "success": True,
            "message": (
                f"Daily limit set to {new_quota} meal(s) per slot"
                if new_quota is not None
                else "Daily limit removed"
            ),
            "daily_meal_quota": provider.daily_meal_quota,
            "current_peak_demand": peak_demand,
        }


    @staticmethod
    def get_daily_quota_status(
        db,
        provider_id: str,
        for_date: date_type = None
    ):

        provider = (
            ProviderRepository.get_by_provider_id(
                db,
                provider_id
            )
        )

        if not provider:

            raise HTTPException(
                status_code=404,
                detail="Provider not found"
            )

        status = PackageCapacityRepository.get_provider_quota_status(
            db,
            provider_id,
            for_date or date_type.today()
        )

        return {
            "success": True,
            **status
        }


    @staticmethod
    def update_address(
        db,
        request
    ):

        provider = ProviderRepository.get_by_provider_id(
            db=db,
            provider_id=request.provider_id
        )

        if not provider:
            return {
                "success": False,
                "message": "Provider not found"
            }

        pincode_check = PincodeService.verify_pincode(
            db=db,
            pincode=request.pincode,
            request=request
        )

        if not pincode_check["serviceable"]:
            return pincode_check

        ProviderRepository.update_provider_address(
            db=db,
            provider=provider,
            request=request
        )

        return {
            "success": True,
            "message": "Address updated successfully"
        }
