from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.repositories.user_repository import UserRepository


class UserProfileService:

    @staticmethod
    def get_profile(
        db: Session,
        user_id: str
    ):

        user = UserRepository.get_by_user_id(
            db,
            user_id
        )

        if not user:

            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        return user

    @staticmethod
    def update_profile(
        db: Session,
        user_id: str,
        payload
    ):

        user = UserRepository.get_by_user_id(
            db,
            user_id
        )

        if not user:

            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        update_data = payload.model_dump(
            exclude_unset=True
        )

        updated_user = UserRepository.update_user(
            db,
            user,
            update_data
        )

        return {
            "success": True,
            "message": "Profile updated successfully",
            "user_id": str(updated_user.user_id),
            "is_profile_completed": (
                updated_user.is_profile_completed
            )
        }
