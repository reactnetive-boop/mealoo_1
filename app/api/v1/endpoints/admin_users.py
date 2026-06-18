from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_user_service import AdminUserService
from app.schemas.admin_schema import (
    AdminUpdateUserStatusRequest,
    AdminWalletAdjustRequest
)

router = APIRouter()


@router.get("")
def list_users(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search by name, phone, or email"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminUserService.list_users(db, status=status, search=search, page=page, limit=limit)


@router.get("/{user_id}")
def get_user_detail(
    user_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminUserService.get_user_detail(db, str(user_id))


@router.put("/{user_id}/status")
def update_user_status(
    user_id: UUID,
    payload: AdminUpdateUserStatusRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminUserService.update_user_status(db, str(user_id), payload, current["admin_id"])


@router.post("/{user_id}/wallet/adjust")
def adjust_user_wallet(
    user_id: UUID,
    payload: AdminWalletAdjustRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminUserService.adjust_wallet(db, str(user_id), payload, current["admin_id"])


@router.put("/subscriptions/{subscription_id}/cancel")
def cancel_subscription(
    subscription_id: UUID,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminUserService.cancel_subscription(db, str(subscription_id), reason, current["admin_id"])
