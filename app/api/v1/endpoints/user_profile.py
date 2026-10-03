from fastapi import APIRouter, Depends, UploadFile, File

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.user_profile_schema import (
    UserProfileResponse,
    UpdateUserProfileRequest,
    UpdateProfileImageResponse
)
from app.services.user_profile_service import UserProfileService

router = APIRouter()


@router.get(
    "/profile",
    response_model=UserProfileResponse,
    summary="Get My Profile",
    description=(
        "**Fetch the logged-in user's profile details.**\n\n"
        "Returns name, phone, email, profile image URL, and account status. "
        "Call this on app launch after login to pre-fill profile screens.\n\n"
        "**Requires:** Bearer token from `POST /user/login`"
    )
)
def get_profile(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return UserProfileService.get_profile(
        db,
        current_user["user_id"]
    )


@router.put(
    "/profile",
    summary="Update My Profile",
    description=(
        "**Update name, email, or other profile fields.**\n\n"
        "Only the fields you send will be updated (partial update supported). "
        "Call `GET /user/profile` after to confirm the changes.\n\n"
        "**Requires:** Bearer token from `POST /user/login`"
    )
)
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


@router.put(
    "/profile/image",
    response_model=UpdateProfileImageResponse,
    summary="Upload Profile Picture",
    description=(
        "**Upload or replace the user's profile photo.**\n\n"
        "Send the image as `multipart/form-data` with field name `file`. "
        "Returns the new image URL. Update your local state with this URL after success.\n\n"
        "**Requires:** Bearer token from `POST /user/login`"
    )
)
def update_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return UserProfileService.update_profile_image(
        db,
        current_user["user_id"],
        file
    )


@router.get(
    "/me/state",
    summary="Customer Account State (drives app navigation)",
    description=(
        "`next_step`: `add_address`, `area_not_serviceable`, `no_kitchens`, `browse` or "
        "`account_inactive`, computed from the saved default address and Orleeno's serviceable "
        "pincodes."
    ),
)
def get_state(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    from app.services.user_menu_service import UserMenuService
    return UserMenuService.customer_state(db, current_user["user_id"])
