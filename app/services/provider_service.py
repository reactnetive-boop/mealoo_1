from fastapi import HTTPException

from app.repositories.provider_repository import (
    ProviderRepository
)


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