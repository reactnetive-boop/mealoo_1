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

        update_data = payload.dict()

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
