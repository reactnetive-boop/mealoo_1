from fastapi import HTTPException, UploadFile

from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.core.errors import DomainError
from app.models.user_model import User
from app.repositories.user_repository import UserRepository
from app.utils.file_helper import save_user_profile_image, delete_upload


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

        dob = update_data.get("date_of_birth")
        if dob is not None and (dob >= today_local() or dob.year < 1900):
            raise DomainError("Enter a valid date of birth")

        email = update_data.get("email")
        if email:
            update_data["email"] = email.strip().lower()
            taken = db.query(User).filter(User.email == update_data["email"], User.user_id != user.user_id).first()
            if taken:
                raise DomainError("This email is already used by another account", 409)
            if update_data["email"] != (user.email or ""):
                update_data["email_verified"] = False

        if update_data.get("full_name") and user.phone:
            update_data["is_profile_completed"] = True

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

        old_path = user.avatar_url
        image_path = save_user_profile_image(file)

        updated_user = UserRepository.update_profile_image(
            db,
            user,
            image_path
        )

        delete_upload(old_path)

        return {
            "success": True,
            "message": "Profile image updated successfully",
            "avatar_url": updated_user.avatar_url
        }
