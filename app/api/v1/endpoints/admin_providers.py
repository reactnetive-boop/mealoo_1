from typing import Optional
from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.services.admin_provider_service import AdminProviderService
from app.schemas.admin_schema import (
    AdminUpdateProviderRequest,
    AdminWalletAdjustRequest,
    AdminMarkUnavailabilityRequest,
    AdminApprovalRequest,
)

router = APIRouter()


@router.get(
    "",
    summary="List All Providers",
    description=(
        "Paginated kitchens. Filter by `search` (name, business name or mobile), `pincode`, "
        "`is_profile_completed`, `approval_status` (`pending` | `approved` | `rejected`) and `is_active`."
    )
)
def list_providers(
    search: Optional[str] = Query(None, max_length=100),
    pincode: Optional[int] = Query(None),
    is_profile_completed: Optional[bool] = Query(None),
    approval_status: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.list_providers(
        db, search=search, pincode=pincode, is_profile_completed=is_profile_completed,
        approval_status=approval_status, is_active=is_active, page=page, limit=limit
    )


@router.get("/{provider_id}", summary="Get Provider Detail")
def get_provider_detail(provider_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminProviderService.get_provider_detail(db, str(provider_id))


@router.put(
    "/{provider_id}/approve",
    summary="Approve Kitchen",
    description=(
        "Approves a kitchen whose profile is complete and whose pincode is an active service area. "
        "Only approved, active kitchens can sell."
    ),
)
def approve_provider(
    provider_id: UUID,
    request: Request,
    payload: Optional[AdminApprovalRequest] = None,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.set_approval(
        db, str(provider_id), approve=True, note=payload.note if payload else None,
        admin_id=current["admin_id"], ip=client_ip(request),
    )


@router.put(
    "/{provider_id}/reject",
    summary="Reject Kitchen Application",
    description="`note` (required) is shown to the kitchen. The kitchen can fix its profile and resubmit.",
)
def reject_provider(
    provider_id: UUID,
    payload: AdminApprovalRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.set_approval(
        db, str(provider_id), approve=False, note=payload.note,
        admin_id=current["admin_id"], ip=client_ip(request),
    )


@router.get(
    "/{provider_id}/daily-quota",
    summary="Get Provider Daily Meal Limit Usage",
    description=(
        "Per meal time on a date (default today): meals committed by subscriptions and one-time orders, "
        "what is still `available` under `daily_meal_quota`, and `is_full`."
    )
)
def get_provider_daily_quota(
    provider_id: UUID,
    quota_date: Optional[date] = Query(None, alias="date", description="Defaults to today"),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.get_daily_quota_status(db, str(provider_id), quota_date)


@router.put(
    "/{provider_id}",
    summary="Update Provider Details",
    description=(
        "Admin corrections to the kitchen profile. `pincode` must be an active service area and cannot change "
        "while subscriptions are running; `daily_meal_quota` cannot go below meals already booked."
    )
)
def update_provider(
    provider_id: UUID,
    payload: AdminUpdateProviderRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.update_provider(db, str(provider_id), payload, current["admin_id"], client_ip(request))


@router.put("/{provider_id}/activate", summary="Activate Provider Account")
def activate_provider(provider_id: UUID, request: Request, db: Session = Depends(get_db), current=Depends(require_super_admin)):
    return AdminProviderService.set_provider_active(db, str(provider_id), True, current["admin_id"], client_ip(request))


@router.put(
    "/{provider_id}/deactivate",
    summary="Deactivate Provider Account",
    description="Signs the kitchen out everywhere and hides it. Blocked while it has running subscriptions. **super_admin**.",
)
def deactivate_provider(provider_id: UUID, request: Request, db: Session = Depends(get_db), current=Depends(require_super_admin)):
    return AdminProviderService.set_provider_active(db, str(provider_id), False, current["admin_id"], client_ip(request))


@router.post(
    "/{provider_id}/wallet/adjust",
    summary="Manually Adjust Provider Earnings Wallet",
    description=(
        "Credit or debit with a mandatory `reason`. Recorded in the kitchen ledger, the platform ledger and the "
        "audit log. Send an `Idempotency-Key` header so a retried request is applied once. **super_admin**."
    )
)
def adjust_provider_wallet(
    provider_id: UUID,
    payload: AdminWalletAdjustRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=100),
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminProviderService.adjust_wallet(
        db, str(provider_id), payload, current["admin_id"], idempotency_key or str(uuid4()), client_ip(request)
    )


@router.put(
    "/{provider_id}/accepting-orders",
    summary="Toggle Provider Order Acceptance",
    description="`accepting=false` stops new subscriptions and one-time orders; running subscriptions continue.",
)
def set_accepting_orders(
    provider_id: UUID,
    request: Request,
    accepting: bool = Query(..., description="true to enable, false to disable"),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.toggle_accepting_orders(db, str(provider_id), accepting, current["admin_id"], client_ip(request))


@router.get("/{provider_id}/unavailability", summary="List Provider Holidays")
def list_unavailability(provider_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminProviderService.list_unavailability(db, str(provider_id))


@router.post(
    "/{provider_id}/unavailability",
    summary="Mark Provider Holiday",
    description=(
        "Blocks new orders for the date. Existing meals stay so they can be reassigned to another kitchen; "
        "whatever is not reassigned by the meal cut-off is cancelled and refunded automatically."
    )
)
def mark_unavailable(
    provider_id: UUID,
    payload: AdminMarkUnavailabilityRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.mark_unavailable(db, str(provider_id), payload, current["admin_id"], client_ip(request))


@router.delete("/{provider_id}/unavailability/{unavailable_date}", summary="Remove Provider Holiday")
def remove_unavailability(
    provider_id: UUID,
    unavailable_date: date,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.remove_unavailability(db, str(provider_id), unavailable_date, current["admin_id"], client_ip(request))
