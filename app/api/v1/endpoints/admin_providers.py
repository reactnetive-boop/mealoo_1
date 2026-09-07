from typing import Optional
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_provider_service import AdminProviderService
from app.schemas.admin_schema import (
    AdminUpdateProviderRequest,
    AdminWalletAdjustRequest,
    AdminMarkUnavailabilityRequest,
)

router = APIRouter()


@router.get(
    "",
    summary="List All Providers",
    description=(
        "**Fetch a paginated list of all registered vendors/kitchens.**\n\n"
        "Filter by `search` (business name or mobile), `pincode`, and/or `is_profile_completed`. "
        "Use this to monitor vendor onboarding and find providers needing attention.\n\n"
        "**When to call:** On the admin vendor management screen."
    )
)
def list_providers(
    search: Optional[str] = Query(None),
    pincode: Optional[int] = Query(None),
    is_profile_completed: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.list_providers(
        db, search=search, pincode=pincode,
        is_profile_completed=is_profile_completed, page=page, limit=limit
    )


@router.get(
    "/{provider_id}",
    summary="Get Provider Detail",
    description=(
        "**Fetch full profile, packages, earnings, and subscription summary for a vendor.**\n\n"
        "Use `provider_id` (UUID) from the providers list."
    )
)
def get_provider_detail(
    provider_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.get_provider_detail(db, str(provider_id))


@router.put(
    "/{provider_id}",
    summary="Update Provider Details",
    description=(
        "**Edit a provider's business name, address, pincode, or other profile fields.**\n\n"
        "Use this for admin-side corrections when the provider cannot update themselves."
    )
)
def update_provider(
    provider_id: UUID,
    payload: AdminUpdateProviderRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.update_provider(db, str(provider_id), payload)


@router.put(
    "/{provider_id}/activate",
    summary="Activate Provider Account",
    description=(
        "**Set a provider account to active, allowing them to receive orders.**\n\n"
        "Use after verifying the provider's documents and profile. "
        "New providers must be activated before they appear in user package listings."
    )
)
def activate_provider(
    provider_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.set_provider_active(db, str(provider_id), True)


@router.put(
    "/{provider_id}/deactivate",
    summary="Deactivate Provider Account",
    description=(
        "**Suspend a provider account, preventing them from appearing in user listings or receiving new orders.**\n\n"
        "Existing active subscriptions are not automatically cancelled — handle those separately."
    )
)
def deactivate_provider(
    provider_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.set_provider_active(db, str(provider_id), False)


@router.post(
    "/{provider_id}/wallet/adjust",
    summary="Manually Adjust Provider Earnings Wallet",
    description=(
        "**Credit or debit a provider's earnings wallet manually.**\n\n"
        "Use for corrections, penalties, or bonus payments. "
        "All adjustments are logged with the admin ID and description for auditing."
    )
)
def adjust_provider_wallet(
    provider_id: UUID,
    payload: AdminWalletAdjustRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.adjust_wallet(db, str(provider_id), payload, current["admin_id"])


@router.put(
    "/{provider_id}/accepting-orders",
    summary="Toggle Provider Order Acceptance",
    description=(
        "**Enable or disable a provider's ability to accept new orders.**\n\n"
        "Pass `accepting=true` to enable or `accepting=false` to pause. "
        "This is separate from account activation — use when a provider temporarily cannot fulfill orders "
        "(e.g. equipment issues) without fully deactivating their account."
    )
)
def set_accepting_orders(
    provider_id: UUID,
    accepting: bool = Query(..., description="true to enable, false to disable"),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.toggle_accepting_orders(db, str(provider_id), accepting)


@router.get(
    "/{provider_id}/unavailability",
    summary="List Provider Unavailability Dates",
    description=(
        "**Fetch all dates when the provider has been marked as unavailable.**\n\n"
        "On these dates no new orders are created and existing scheduled orders may be skipped. "
        "Use before marking new unavailability to avoid duplicates."
    )
)
def list_unavailability(
    provider_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.list_unavailability(db, str(provider_id))


@router.post(
    "/{provider_id}/unavailability",
    summary="Mark Provider as Unavailable on a Date",
    description=(
        "**Block a specific date for a provider (e.g. public holiday, equipment maintenance).**\n\n"
        "Orders scheduled for that date will be treated as skipped. "
        "Provide `unavailable_date` (YYYY-MM-DD) and an optional `reason`."
    )
)
def mark_unavailable(
    provider_id: UUID,
    payload: AdminMarkUnavailabilityRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.mark_unavailable(db, str(provider_id), payload)


@router.delete(
    "/{provider_id}/unavailability/{unavailable_date}",
    summary="Remove Provider Unavailability Date",
    description=(
        "**Remove a previously set unavailability date for a provider.**\n\n"
        "Use if the provider confirms they can fulfill orders on that date after all. "
        "Scheduled orders for that date may need to be manually reinstated."
    )
)
def remove_unavailability(
    provider_id: UUID,
    unavailable_date: date,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminProviderService.remove_unavailability(db, str(provider_id), unavailable_date)
