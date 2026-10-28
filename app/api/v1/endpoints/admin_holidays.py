from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.dependencies.auth_dependency import get_current_admin
from app.services.holiday_request_service import HolidayRequestService
from app.services.vendor_holiday_service import VendorHolidayService

router = APIRouter()


class HolidayDecisionRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=500)


class HolidayDeleteRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


@router.get(
    "",
    summary="Kitchen Holiday History",
    description=(
        "Every planned and emergency holiday of every kitchen (newest first) with affected subscriptions and "
        "meals, replacements, compensations and failures. Filters: provider, type, date range, processing status."
    ),
)
def list_holidays(
    provider_id: Optional[UUID] = Query(None),
    holiday_type: Optional[str] = Query(None, pattern="^(casual|emergency)$"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    processing_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin),
):
    return VendorHolidayService.admin_list(
        db, provider_id=provider_id, holiday_type=holiday_type, from_date=from_date, to_date=to_date,
        processing_status=processing_status, page=page, limit=limit,
    )


@router.get(
    "/meals",
    summary="Emergency Holiday Meals",
    description=(
        "Meals affected by emergency holidays: replacement assignments, no-replacement cases with their skip "
        "credit and wallet refund references, and failed processing or notifications (`status=failed`)."
    ),
)
def holiday_meals(
    outcome: Optional[str] = Query(None, pattern="^(pending|replaced|compensated|not_affected|failed)$"),
    status: Optional[str] = Query(None, pattern="^(failed|pending)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin),
):
    return VendorHolidayService.admin_compensations(db, outcome=outcome, status=status, page=page, limit=limit)


@router.get(
    "/requests",
    summary="Kitchen Holiday Requests",
    description=(
        "Emergency and regular (weekly) holiday requests of every kitchen, pending first then newest. "
        "Filters: status (pending | approved | rejected | withdrawn | expired), type, provider. `pending` "
        "is the number waiting across all kitchens."
    ),
)
def list_requests(
    status: Optional[str] = Query(None, pattern="^(pending|approved|rejected|withdrawn|expired)$"),
    request_type: Optional[str] = Query(None, pattern="^(emergency|regular)$"),
    provider_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin),
):
    return HolidayRequestService.admin_list(db, status=status, request_type=request_type, provider_id=provider_id,
                                            page=page, limit=limit)


@router.get(
    "/requests/{request_id}",
    summary="Kitchen Holiday Request Detail",
    description=(
        "The request, what approving it would do now (`impact_now`), the kitchen's current approved schedule, "
        "its earlier requests and every notice sent about it."
    ),
)
def request_detail(request_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return HolidayRequestService.admin_detail(db, request_id)


@router.post(
    "/requests/{request_id}/approve",
    summary="Approve a Kitchen Holiday Request",
    description=(
        "Applies the change. Emergency: the kitchen is closed that day - or only for the meals requested "
        "(`meal_slots` kept as asked) - affected meals and one-time orders are refunded to the wallet, every "
        "active subscription gets 1 extra free skip, customers, the kitchen and its delivery partners are "
        "notified. Regular: running subscriptions are re-planned (no paid meal lost) and customers and partners "
        "are notified; a change or removal that would now touch a running subscription is refused (409 "
        "HOLIDAY_CHANGE_BLOCKED) and the request stays pending. Approving twice changes nothing."
    ),
)
def approve_request(request_id: UUID, request: Request, payload: Optional[HolidayDecisionRequest] = None,
                    db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return HolidayRequestService.approve(db, request_id, current["admin_id"], payload.note if payload else None,
                                         client_ip(request))


@router.post(
    "/requests/{request_id}/reject",
    summary="Reject a Kitchen Holiday Request",
    description="Nothing changes in the kitchen's schedule; the kitchen is told (with the note, if given).",
)
def reject_request(request_id: UUID, request: Request, payload: Optional[HolidayDecisionRequest] = None,
                   db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return HolidayRequestService.reject(db, request_id, current["admin_id"], payload.note if payload else None,
                                        client_ip(request))


@router.get("/{holiday_id}", summary="Kitchen Holiday Detail")
def holiday_detail(holiday_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return VendorHolidayService.admin_detail(db, holiday_id)


@router.delete(
    "/{holiday_id}",
    summary="Delete an Emergency Holiday",
    description=(
        "Only before the delivery time of the holiday's earliest blocked meal (for a full-day holiday the "
        "earliest meal the kitchen serves), business-local time - `delete_cutoff_at` / `deletable` on the "
        "holiday. At or after it: 409 HOLIDAY_DELETE_CUTOFF_PASSED and nothing changes. The meals open again for "
        "new orders; refunds and free skips already given stay with the customers, cancelled meals stay "
        "cancelled; customers, partners and the kitchen are told."
    ),
)
def delete_holiday(holiday_id: UUID, request: Request, payload: Optional[HolidayDeleteRequest] = None,
                   db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return VendorHolidayService.admin_delete(db, holiday_id, current["admin_id"], payload.reason if payload else None,
                                             client_ip(request))


@router.post(
    "/{holiday_id}/retry",
    summary="Retry an Emergency Holiday",
    description=(
        "Processes meals that failed or were interrupted and re-sends notices that failed. Meals already "
        "processed are never processed again, and every wallet / skip credit has its own idempotency key, so "
        "a retry can never create a duplicate transaction."
    ),
)
def retry_holiday(holiday_id: UUID, request: Request, db: Session = Depends(get_db),
                  current=Depends(get_current_admin)):
    return VendorHolidayService.admin_retry(db, holiday_id, current["admin_id"], client_ip(request))
