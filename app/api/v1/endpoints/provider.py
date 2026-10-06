from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    UploadFile,
    File
)

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip, limit_by_ip
from app.services.service_area_service import ServiceAreaService
from app.dependencies.auth_dependency import (
    get_provider_session,
    get_active_provider,
    get_current_provider,
)
from app.schemas.provider_schema import (
    CompleteProfileRequest,
    ProviderProfileResponse,
    UpdateProfileImageResponse,
    ProviderAddressUpdateRequest,
    UpdateDailyQuotaRequest,
    UpdateDailyQuotaResponse,
    DailyQuotaStatusResponse,
    AcceptingOrdersRequest,
    HolidayRequest,
)
from app.services.provider_service import ProviderService
from app.services.provider_order_service import ProviderOrderService
from app.services.provider_notification_service import ProviderNotificationService

router = APIRouter()


@router.get(
    "/me/state",
    summary="Kitchen Account State (drives app navigation)",
    description=(
        "Returns the account flags and `next_step`: `complete_profile`, `account_inactive`, "
        "`awaiting_approval`, `approval_rejected` or `dashboard`. Call on app start, after "
        "login and on refresh; show the screen for `next_step`."
    ),
)
def get_state(db: Session = Depends(get_db), current_provider=Depends(get_provider_session)):
    return ProviderService.get_state(db, current_provider["provider_id"])


@router.put(
    "/complete-profile",
    summary="Complete Provider Profile",
    description=(
        "All business and address fields are required, the pincode must be one Orleeno serves, "
        "and the daily meal quota cannot be lower than meals already booked. On success the "
        "kitchen enters the admin approval queue."
    ),
)
def complete_profile(
    payload: CompleteProfileRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_provider_session),
):
    return ProviderService.complete_profile(db, current_provider["provider_id"], payload)


@router.get(
    "/profile",
    response_model=ProviderProfileResponse,
    summary="Get Provider Profile",
)
def get_profile(db: Session = Depends(get_db), current_provider=Depends(get_provider_session)):
    return ProviderService.get_profile(db, current_provider["provider_id"])


@router.put(
    "/profile/image",
    response_model=UpdateProfileImageResponse,
    summary="Upload Provider Profile Image",
    description="JPEG, PNG or WEBP up to 5 MB, as `multipart/form-data` field `file`.",
)
def update_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_provider=Depends(get_active_provider),
):
    return ProviderService.update_profile_image(db, current_provider["provider_id"], file)


@router.put(
    "/daily-quota",
    response_model=UpdateDailyQuotaResponse,
    summary="Set Provider Daily Meal Limit",
    description=(
        "Meals per meal-slot per day across all packages. Cannot go below the meals already "
        "booked for any upcoming day. Send null to remove the limit."
    ),
)
def update_daily_quota(
    payload: UpdateDailyQuotaRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_active_provider),
):
    return ProviderService.update_daily_quota(db, current_provider["provider_id"], payload)


@router.get(
    "/daily-quota",
    response_model=DailyQuotaStatusResponse,
    summary="Get Daily Meal Limit Usage",
    description="Meals booked per slot on a date (defaults to today), from the actual meal rows.",
)
def get_daily_quota_status(
    quota_date: Optional[date] = Query(None, alias="date", description="Defaults to today"),
    db: Session = Depends(get_db),
    current_provider=Depends(get_active_provider),
):
    return ProviderService.get_daily_quota_status(db, current_provider["provider_id"], quota_date)


@router.put(
    "/address",
    summary="Update Provider Address",
    description="The kitchen comes from the session. The pincode must be one Orleeno serves.",
)
def update_provider_address(
    request: ProviderAddressUpdateRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_provider_session),
):
    return ProviderService.update_address(db, current_provider["provider_id"], request)


@router.put(
    "/accepting-orders",
    summary="Pause / Resume New Orders",
    description="While paused the kitchen is hidden from customers and new orders are refused.",
)
def set_accepting_orders(
    payload: AcceptingOrdersRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return ProviderService.set_accepting_orders(db, current_provider["provider_id"], payload.accepting)


@router.get("/holidays", summary="List Kitchen Holidays")
def list_holidays(db: Session = Depends(get_db), current_provider=Depends(get_current_provider)):
    return ProviderService.list_holidays(db, current_provider["provider_id"])


@router.post(
    "/holidays",
    summary="Mark a Holiday",
    description="No new orders are accepted for that date; existing orders are moved or refunded.",
)
def add_holiday(
    payload: HolidayRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return ProviderService.add_holiday(db, current_provider["provider_id"], payload.date, payload.reason)


@router.delete("/holidays/{holiday_date}", summary="Remove a Holiday")
def remove_holiday(
    holiday_date: date,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return ProviderService.remove_holiday(db, current_provider["provider_id"], holiday_date)


@router.get(
    "/delivery-partners",
    summary="Delivery Partners This Kitchen Can Assign",
    description="Approved, active partners attached to this kitchen or to the shared pool.",
)
def list_delivery_partners(db: Session = Depends(get_db), current_provider=Depends(get_current_provider)):
    return ProviderService.assignable_delivery_partners(db, current_provider["provider_id"])


@router.get(
    "/pickup-code",
    summary="Today's Pickup Code",
    description=(
        "The kitchen's 6-digit pickup code for today (business date). Read it out to the delivery "
        "partner when handing over today's orders; the partner enters it to record the pickup. It "
        "works only for this kitchen and only today, and it is never shown to partners or customers."
    ),
)
def get_pickup_code(db: Session = Depends(get_db), current_provider=Depends(get_current_provider)):
    return ProviderOrderService.get_pickup_code(db, current_provider["provider_id"])


@router.post(
    "/pickup-code/regenerate",
    summary="Replace Today's Pickup Code",
    description="Use when the code was shared with the wrong person. The old code stops working at once.",
    dependencies=[Depends(limit_by_ip("pickup_code_regenerate", 5, 3600))],
)
def regenerate_pickup_code(request: Request, db: Session = Depends(get_db), current_provider=Depends(get_current_provider)):
    return ProviderOrderService.regenerate_pickup_code(db, current_provider["provider_id"], client_ip(request))


@router.get(
    "/notifications",
    summary="Kitchen Notifications",
    description=(
        "Newest first, with the `unread` count for the bell badge. Types: `new_subscription`, `new_order`, "
        "`partner_assigned`, `partner_unassigned`, `pickup_pending`. `data` carries `subscription_id` or "
        "`order_id` + `kind` to open the related screen."
    ),
)
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_provider=Depends(get_active_provider),
):
    return ProviderNotificationService.list(db, current_provider["provider_id"], limit=limit, unread_only=unread_only)


@router.put("/notifications/read-all", summary="Mark All Kitchen Notifications Read")
def mark_all_notifications_read(db: Session = Depends(get_db), current_provider=Depends(get_active_provider)):
    return ProviderNotificationService.mark_all_read(db, current_provider["provider_id"])


@router.put("/notifications/{notification_id}/read", summary="Mark a Kitchen Notification Read")
def mark_notification_read(notification_id: UUID, db: Session = Depends(get_db), current_provider=Depends(get_active_provider)):
    return ProviderNotificationService.mark_read(db, current_provider["provider_id"], notification_id)


@router.get(
    "/service-areas",
    summary="My Delivery Areas",
    description="Pincodes this kitchen delivers to: its own plus those Orleeno added. Contact Orleeno to change them.",
)
def my_service_areas(db: Session = Depends(get_db), current_provider=Depends(get_provider_session)):
    return ServiceAreaService.list(db, current_provider["provider_id"])
