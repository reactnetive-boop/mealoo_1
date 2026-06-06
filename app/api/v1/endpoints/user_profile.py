from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.user_profile_schema import (
    UserProfileResponse,
    UpdateUserProfileRequest
)
from app.services.user_profile_service import UserProfileService

router = APIRouter()


@router.get(
    "/profile",
    response_model=UserProfileResponse
)
def get_profile(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return UserProfileService.get_profile(
        db,
        current_user["user_id"]
    )


@router.put("/profile")
def update_profile(
    payload: UpdateUserProfileRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return UserProfileService.update_profile(
        db,
        current_user["user_id"],
        payload
    )
