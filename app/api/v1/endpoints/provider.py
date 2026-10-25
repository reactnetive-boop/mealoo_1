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
    EmergencyHolidayRequest,
)
from app.services.vendor_holiday_service import VendorHolidayService
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


@router.get(
    "/holidays",
    summary="Kitchen Holidays and Calendar",
    description=(
        "Current holiday rules (`rules`), past ones, emergency declarations, the holiday calendar from 30 days "
        "back to 120 days ahead (`calendar`, also as `holidays` for older apps), and `weekly_holiday_set` for "
        "the onboarding question. Dates are business-local (Asia/Kolkata)."
    ),
)
def list_holidays(db: Session = Depends(get_db), current_provider=Depends(get_current_provider)):
    return VendorHolidayService.overview(db, current_provider["provider_id"])


@router.post(
    "/holidays/preview",
    summary="Preview a Planned Holiday",
    description="How many running subscriptions and meals the holiday would re-plan. Nothing is saved.",
)
def preview_holiday(payload: HolidayRequest, db: Session = Depends(get_db),
                    current_provider=Depends(get_current_provider)):
    return VendorHolidayService.preview_casual(db, current_provider["provider_id"], payload.rule())


@router.post(
    "/holidays",
    summary="Plan a Holiday",
    description=(
        "Every Sunday, weekends, selected weekdays, specific dates, a date range or days of the month, from "
        "tomorrow on. Running subscriptions are re-planned at once: no meal and no charge on those days, plans "
        "move past them, customers are told in advance. Same-day closures: use the emergency holiday."
    ),
)
def add_holiday(payload: HolidayRequest, db: Session = Depends(get_db),
                current_provider=Depends(get_current_provider)):
    pid = current_provider["provider_id"]
    return VendorHolidayService.add_casual(db, pid, payload.rule(), actor_type="provider", actor_id=pid)


@router.put("/holidays/rules/{holiday_id}", summary="Edit a Future Holiday")
def update_holiday(holiday_id: UUID, payload: HolidayRequest, db: Session = Depends(get_db),
                   current_provider=Depends(get_current_provider)):
    pid = current_provider["provider_id"]
    return VendorHolidayService.update_casual(db, pid, holiday_id, payload.rule(), actor_type="provider", actor_id=pid)


@router.delete("/holidays/rules/{holiday_id}", summary="Remove a Future Holiday")
def remove_holiday_rule(holiday_id: UUID, db: Session = Depends(get_db),
                        current_provider=Depends(get_current_provider)):
    pid = current_provider["provider_id"]
    return VendorHolidayService.remove(db, pid, holiday_id, actor_type="provider", actor_id=pid)


@router.get(
    "/holidays/emergency/preview",
    summary="Preview an Emergency Holiday",
    description="Orders and subscriptions an emergency closure on `date` (default today) would affect.",
)
def preview_emergency(date_: Optional[date] = Query(None, alias="date"), db: Session = Depends(get_db),
                      current_provider=Depends(get_current_provider)):
    return VendorHolidayService.preview_emergency(db, current_provider["provider_id"], date_)


@router.post(
    "/holidays/emergency",
    summary="Declare an Emergency Holiday",
    description=(
        "The kitchen cannot cook on `date` (default today; never the past). No new work lands on it; each "
        "affected meal goes to a replacement kitchen (same PIN code, same or lower price) or the customer gets "
        "one extra skip plus the meal's value in the wallet. Subscriptions are not cancelled."
    ),
)
def declare_emergency(payload: EmergencyHolidayRequest, db: Session = Depends(get_db),
                      current_provider=Depends(get_current_provider)):
    pid = current_provider["provider_id"]
    return VendorHolidayService.declare_emergency(db, pid, payload.date, payload.reason,
                                                  actor_type="provider", actor_id=pid)


@router.get("/holidays/{holiday_id}/affected", summary="Orders Affected by a Holiday")
def holiday_affected_orders(holiday_id: UUID, db: Session = Depends(get_db),
                            current_provider=Depends(get_current_provider)):
    return VendorHolidayService.affected_orders(db, current_provider["provider_id"], holiday_id)


@router.delete("/holidays/{holiday_date}", summary="Remove a Holiday Date (older apps)")
def remove_holiday(
    holiday_date: date,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    pid = current_provider["provider_id"]
    return VendorHolidayService.remove_date(db, pid, holiday_date, actor_type="provider", actor_id=pid)


@router.get(
    "/delivery-partner",
    summary="My Kitchen's Delivery Partner",
    description=(
        "The delivery partner Orleeno assigned to this kitchen. New one-time orders, new subscriptions and "
        "daily subscription meals go to them automatically. `delivery_partner` is null when none is assigned."
    ),
)
def get_kitchen_delivery_partner(db: Session = Depends(get_db), current_provider=Depends(get_current_provider)):
    return ProviderService.kitchen_delivery_partner(db, current_provider["provider_id"])


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
        "works only for this kitchen and only today, and it is never shown to partners or customers. "
        "A code is generated only once the kitchen has an order for today; until then this returns "
        "404 with code NO_PICKUP_CODE and nothing is stored."
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
