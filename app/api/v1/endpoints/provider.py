from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File
)

from sqlalchemy.orm import Session

from app.core.database import (
    get_db
)

from app.dependencies.auth_dependency import (
    get_current_provider
)

from app.schemas.provider_schema import (
    CompleteProfileRequest,
    ProviderProfileResponse,
    UpdateProfileImageResponse,
    ProviderAddressUpdateRequest
)

from app.services.provider_service import (
    ProviderService
)

router = APIRouter()


@router.put(
    "/complete-profile",
    summary="Complete Provider Profile",
    description=(
        "**Fill in business details after the provider's first login.**\n\n"
        "Required fields: business name, FSSAI number, address, pincode, meal types offered. "
        "This must be completed before the provider can create packages or appear in user listings.\n\n"
        "**When to call:** Immediately after the first `POST /provider/login`. "
        "Check `GET /provider/profile` to see if the profile is already complete."
    )
)
def complete_profile(
    payload: CompleteProfileRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(
        get_current_provider
    )
):

    return (
        ProviderService.complete_profile(
            db,
            current_provider["provider_id"],
            payload
        )
    )


@router.get(
    "/profile",
    response_model=ProviderProfileResponse,
    summary="Get Provider Profile",
    description=(
        "**Fetch the logged-in provider's full profile.**\n\n"
        "Returns business name, mobile, address, pincode, service areas, meal types, "
        "profile image, and account status.\n\n"
        "**When to call:** On the provider dashboard home screen or when navigating to profile settings."
    )
)
def get_profile(
    db: Session = Depends(get_db),
    current_provider=Depends(
        get_current_provider
    )
):

    return (
        ProviderService.get_profile(
            db,
            current_provider["provider_id"]
        )
    )


@router.put(
    "/profile/image",
    response_model=UpdateProfileImageResponse,
    summary="Upload Provider Profile Image",
    description=(
        "**Upload or replace the provider's business profile photo.**\n\n"
        "Send the image as `multipart/form-data` with field name `file`. "
        "Returns the new image URL. This image is shown to users on the package listing screen."
    )
)
async def update_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_provider=Depends(
        get_current_provider
    )
):

    response = (
        ProviderService.update_profile_image(
            db,
            current_provider["provider_id"],
            file
        )
    )

    return response


@router.put(
    "/address",
    summary="Update Provider Address",
    description=(
        "**Update the provider's registered business address and pincode.**\n\n"
        "The pincode determines which user delivery areas the provider appears in. "
        "Changes take effect immediately for new users browsing packages."
    )
)
async def update_provider_address(
    request: ProviderAddressUpdateRequest,
    db: Session = Depends(get_db)
):

    return ProviderService.update_address(
        db=db,
        request=request
    )
