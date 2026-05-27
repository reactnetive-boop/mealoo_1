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
    "/complete-profile"
)
def complete_profile(
    payload: CompleteProfileRequest,
    db: Session = Depends(get_db),
    current_provider = Depends(
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
    response_model=ProviderProfileResponse
)
def get_profile(
    db: Session = Depends(get_db),
    current_provider = Depends(
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
    response_model=(
        UpdateProfileImageResponse
    )
)
async def update_profile_image(
    provider_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    response = (
        ProviderService.update_profile_image(
            db,
            provider_id,
            file
        )
    )

    return response

@router.put("/address")
async def update_provider_address(
    request: ProviderAddressUpdateRequest,
    db: Session = Depends(get_db)
):

    return ProviderService.update_address(
        db=db,
        request=request
    )