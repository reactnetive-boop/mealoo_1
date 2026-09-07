from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.services.admin_user_service import AdminUserService
from app.schemas.admin_schema import (
    AdminUpdateUserStatusRequest,
    AdminWalletAdjustRequest
)

router = APIRouter()


@router.get(
    "",
    summary="List All Users",
    description=(
        "**Fetch a paginated list of all registered users.**\n\n"
        "Filter by `status` (`active`, `suspended`) and/or search by name, phone, or email. "
        "Use `page` and `limit` for pagination (default: 20 per page).\n\n"
        "**When to call:** On the admin user management screen."
    )
)
def list_users(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search by name, phone, or email"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminUserService.list_users(db, status=status, search=search, page=page, limit=limit)


@router.get(
    "/{user_id}",
    summary="Get User Detail",
    description=(
        "**Fetch full profile, subscription history, wallet balance, and order summary for a user.**\n\n"
        "Use `user_id` (UUID) from the users list. "
        "Use this before taking any action on the user account."
    )
)
def get_user_detail(
    user_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminUserService.get_user_detail(db, str(user_id))


@router.put(
    "/{user_id}/status",
    summary="Update User Status",
    description=(
        "**Activate or suspend a user account.**\n\n"
        "Set `status` to `active` or `suspended`. Suspended users cannot log in or place orders. "
        "Provide a `reason` for audit trail purposes.\n\n"
        "**Requires:** `super_admin` role."
    )
)
def update_user_status(
    user_id: UUID,
    payload: AdminUpdateUserStatusRequest,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminUserService.update_user_status(db, str(user_id), payload, current["admin_id"])


@router.post(
    "/{user_id}/wallet/adjust",
    summary="Manually Adjust User Wallet",
    description=(
        "**Credit or debit a user's wallet balance manually.**\n\n"
        "Use for refunds, compensation, or corrections. "
        "Send `amount` (positive for credit, use negative for debit), `type` (`credit`/`debit`), "
        "and `description` (reason for the adjustment — stored in transaction history).\n\n"
        "**Requires:** Admin authentication. All adjustments are logged."
    )
)
def adjust_user_wallet(
    user_id: UUID,
    payload: AdminWalletAdjustRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminUserService.adjust_wallet(db, str(user_id), payload, current["admin_id"])


@router.put(
    "/subscriptions/{subscription_id}/cancel",
    summary="Admin Cancel Subscription",
    description=(
        "**Force-cancel a user's subscription on their behalf.**\n\n"
        "Use when the user is unable to cancel themselves, or for policy reasons. "
        "Provide an optional `reason` query parameter for the audit log.\n\n"
        "**Requires:** Admin authentication."
    )
)
def cancel_subscription(
    subscription_id: UUID,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminUserService.cancel_subscription(db, str(subscription_id), reason, current["admin_id"])
