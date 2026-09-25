from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    Query,
    UploadFile,
    File
)

from typing import Optional

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
    ProviderAddressUpdateRequest,
    UpdateDailyQuotaRequest,
    UpdateDailyQuotaResponse,
    DailyQuotaStatusResponse
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
        "Required fields: business name, address, pincode, meal types offered. "
        "Optional: `fssai_licence` (14 digits) and `daily_meal_quota` (meals servable per slot per day). "
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
    "/daily-quota",
    response_model=UpdateDailyQuotaResponse,
    summary="Set Provider Daily Meal Limit",
    description=(
        "**Cap how many meals this kitchen can serve per meal-slot per day, across all packages.**\n\n"
        "`daily_meal_quota = 15` means 15 breakfasts **and** 15 lunches **and** 15 dinners per day, "
        "whatever mix of packages those meals come from. Once a slot is full, new subscriptions, "
        "package switches and one-time orders for that slot are rejected with `400`.\n\n"
        "This sits on top of the per-package limit set by `PUT /provider-package/capacity` — "
        "an order must fit inside both.\n\n"
        "Send `daily_meal_quota=null` to remove the limit.\n\n"
        "**Validation:** the new limit cannot be lower than the meals already committed to active "
        "subscriptions (the response returns that figure as `current_peak_demand`).\n\n"
        "**When to call:** From kitchen settings, whenever capacity changes (staff shortage, festival rush)."
    )
)
def update_daily_quota(
    payload: UpdateDailyQuotaRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(
        get_current_provider
    )
):

    return ProviderService.update_daily_quota(
        db,
        current_provider["provider_id"],
        payload
    )


@router.get(
    "/daily-quota",
    response_model=DailyQuotaStatusResponse,
    summary="Get Daily Meal Limit Usage",
    description=(
        "**How much of the daily limit is used up for each meal-slot.**\n\n"
        "Per slot it returns meals committed by active subscriptions, meals from one-time orders "
        "on that date, the total, how many are still `available`, and `is_full`.\n\n"
        "`available` is `null` and `is_full` is `false` when the provider has no limit set.\n\n"
        "Defaults to today; pass `?date=YYYY-MM-DD` to look ahead.\n\n"
        "**When to call:** On the provider dashboard home screen, to show remaining slots for the day."
    )
)
def get_daily_quota_status(
    quota_date: Optional[date] = Query(
        None,
        alias="date",
        description="Defaults to today"
    ),
    db: Session = Depends(get_db),
    current_provider=Depends(
        get_current_provider
    )
):

    return ProviderService.get_daily_quota_status(
        db,
        current_provider["provider_id"],
        quota_date
    )


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
