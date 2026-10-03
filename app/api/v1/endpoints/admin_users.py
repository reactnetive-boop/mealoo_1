from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.services.admin_user_service import AdminUserService
from app.schemas.admin_schema import AdminUpdateUserStatusRequest, AdminWalletAdjustRequest

router = APIRouter()


@router.get(
    "",
    summary="List All Users",
    description="Filter by `status` (`active`, `inactive`, `suspended`) and search by name, phone or email.",
)
def list_users(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=100, description="Search by name, phone, or email"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminUserService.list_users(db, status=status, search=search, page=page, limit=limit)


@router.get("/{user_id}", summary="Get User Detail")
def get_user_detail(user_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminUserService.get_user_detail(db, str(user_id))


@router.put(
    "/{user_id}/status",
    summary="Update User Status",
    description=(
        "`active` | `inactive` | `suspended`. Blocking signs the customer out everywhere and is refused while "
        "they have running subscriptions. **super_admin**."
    ),
)
def update_user_status(
    user_id: UUID,
    payload: AdminUpdateUserStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminUserService.update_user_status(db, str(user_id), payload, current["admin_id"], client_ip(request))


@router.post(
    "/{user_id}/wallet/adjust",
    summary="Manually Adjust User Wallet",
    description=(
        "Credit or debit (`type`) with a mandatory `reason`. Recorded in the customer ledger, platform ledger and "
        "audit log. Send `Idempotency-Key` so retries apply once. A debit never takes the balance below 0. "
        "**super_admin**."
    ),
)
def adjust_user_wallet(
    user_id: UUID,
    payload: AdminWalletAdjustRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=100),
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminUserService.adjust_wallet(
        db, str(user_id), payload, current["admin_id"], idempotency_key or str(uuid4()), client_ip(request)
    )


@router.put(
    "/subscriptions/{subscription_id}/cancel",
    summary="Admin Cancel Subscription",
    description=(
        "Cancels the subscription, cancels every meal that has not started and refunds them to the customer's "
        "wallet. Audited. **super_admin**."
    ),
)
def cancel_subscription(
    subscription_id: UUID,
    request: Request,
    reason: Optional[str] = Query(None, max_length=500),
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminUserService.cancel_subscription(db, str(subscription_id), reason, current["admin_id"], client_ip(request))
