from fastapi import HTTPException, UploadFile

from sqlalchemy.orm import Session

from app.repositories.user_repository import UserRepository
from app.utils.file_helper import save_user_profile_image


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

    @staticmethod
    def update_profile_image(
        db: Session,
        user_id: str,
        file: UploadFile
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

        allowed_extensions = ["jpg", "jpeg", "png", "webp"]

        file_extension = (
            file.filename.split(".")[-1].lower()
        )

        if file_extension not in allowed_extensions:

            raise HTTPException(
                status_code=400,
                detail="Invalid image format. Allowed: jpg, jpeg, png, webp"
            )

        image_path = save_user_profile_image(file)

        updated_user = UserRepository.update_profile_image(
            db,
            user,
            image_path
        )

        return {
            "success": True,
            "message": "Profile image updated successfully",
            "avatar_url": updated_user.avatar_url
        }
