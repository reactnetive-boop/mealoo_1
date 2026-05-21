from fastapi import (
    APIRouter,
    Depends
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
    ProviderProfileResponse
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