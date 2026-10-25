from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.dependencies.auth_dependency import get_current_admin
from app.services.vendor_holiday_service import VendorHolidayService

router = APIRouter()


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


@router.get("/{holiday_id}", summary="Kitchen Holiday Detail")
def holiday_detail(holiday_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return VendorHolidayService.admin_detail(db, holiday_id)


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
