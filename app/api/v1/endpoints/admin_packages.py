from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.services.admin_content_service import AdminPackageService
from app.schemas.admin_schema import (
    AdminCreatePackageRequest,
    AdminUpdatePackageRequest,
    AdminPackageSubscriptionToggleRequest,
    AdminApprovalRequest,
)

router = APIRouter()


@router.post(
    "",
    summary="Create Orleeno Catalogue Package",
    description=(
        "Creates an approved, ready-made package. Kitchens offer it with `POST /provider-package/select` and set "
        "their own daily capacity; customers then buy it from those kitchens. **super_admin**."
    )
)
def create_package(
    payload: AdminCreatePackageRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminPackageService.create_package(db, payload, current["admin_id"], client_ip(request))


@router.get(
    "",
    summary="List All Packages (Admin View)",
    description=(
        "Filter by `is_predefined`, `is_active`, `is_subscription_available`, `approval_status` "
        "(`pending` = waiting for review), `provider_id` or `search`. Deleted packages are hidden unless "
        "`include_deleted=true`."
    )
)
def list_packages(
    is_predefined: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(None),
    is_subscription_available: Optional[bool] = Query(None),
    approval_status: Optional[str] = Query(None, pattern="^(pending|approved|rejected)$"),
    provider_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None, max_length=100),
    include_deleted: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.list_packages(
        db, is_predefined=is_predefined, is_active=is_active,
        is_subscription_available=is_subscription_available, approval_status=approval_status,
        provider_id=str(provider_id) if provider_id else None,
        search=search, include_deleted=include_deleted, page=page, limit=limit
    )


@router.get("/{package_id}", summary="Get Package Detail (Admin View)")
def get_package(package_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminPackageService.get_package(db, str(package_id))


@router.put(
    "/{package_id}/approve",
    summary="Approve Package",
    description="Makes the package live. Requires at least one item and valid prices.",
)
def approve_package(
    package_id: UUID,
    request: Request,
    payload: Optional[AdminApprovalRequest] = None,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.set_approval(
        db, str(package_id), approve=True, note=payload.note if payload else None,
        admin_id=current["admin_id"], ip=client_ip(request),
    )


@router.put(
    "/{package_id}/reject",
    summary="Reject Package",
    description="`note` (required) is shown to the kitchen. Running subscriptions continue at their booked price.",
)
def reject_package(
    package_id: UUID,
    payload: AdminApprovalRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.set_approval(
        db, str(package_id), approve=False, note=payload.note,
        admin_id=current["admin_id"], ip=client_ip(request),
    )


@router.put(
    "/{package_id}",
    summary="Update Package (Admin)",
    description=(
        "Edit content, prices or `is_active` / `is_available`. `is_active=false` stops new sales immediately; "
        "running subscriptions keep their booked price. Prices: `discounted_price` (selling price) and "
        "`subscription_price` must not exceed `price`; send 0 to clear them."
    )
)
def update_package(
    package_id: UUID,
    payload: AdminUpdatePackageRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.update_package(db, str(package_id), payload, current["admin_id"], client_ip(request))


@router.patch(
    "/{package_id}/subscription",
    summary="Enable / Disable Package Subscription (Admin)",
    description=(
        "`is_subscription_available=true` opens the package for subscription (charged `subscription_price`, or the selling price when unset). `false` blocks new "
        "subscriptions and switches; running subscriptions continue."
    )
)
def set_package_subscription(
    package_id: UUID,
    payload: AdminPackageSubscriptionToggleRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.set_subscription_availability(
        db, str(package_id), payload, current["admin_id"], client_ip(request)
    )


@router.delete(
    "/{package_id}",
    summary="Delete Package (Admin)",
    description=(
        "Soft delete: hidden everywhere, history kept. Refused while the package has running subscriptions or "
        "open one-time orders. **super_admin**."
    )
)
def delete_package(package_id: UUID, request: Request, db: Session = Depends(get_db), current=Depends(require_super_admin)):
    return AdminPackageService.delete_package(db, str(package_id), current["admin_id"], client_ip(request))
