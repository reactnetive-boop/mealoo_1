from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.services.admin_delivery_boy_service import AdminDeliveryBoyService
from app.schemas.admin_schema import (
    AdminUpdateDeliveryBoyRequest, AdminApprovalRequest, AdminDocumentReviewRequest,
    AdminAssignVendorRequest, AdminRemoveVendorRequest,
)

router = APIRouter()


@router.get(
    "",
    summary="List Delivery Partners",
    description="Filter by `search` (name or mobile), `is_active`, `provider_id` and `approval_status`.",
)
def list_delivery_boys(
    search: Optional[str] = Query(None, max_length=100),
    is_active: Optional[bool] = Query(None),
    provider_id: Optional[UUID] = Query(None),
    approval_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.list_delivery_boys(
        db, search=search, is_active=is_active,
        provider_id=str(provider_id) if provider_id else None,
        approval_status=approval_status, page=page, limit=limit
    )


@router.get(
    "/{delivery_boy_id}",
    summary="Delivery Partner Detail",
    description="Profile, document review status, masked payout details and delivery stats.",
)
def get_delivery_boy_detail(delivery_boy_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminDeliveryBoyService.get_delivery_boy_detail(db, str(delivery_boy_id))


@router.get(
    "/{delivery_boy_id}/documents/{document_id}/file",
    summary="View a KYC Document",
    description="Streams the private file. Every view is written to the audit log.",
)
def get_document_file(
    delivery_boy_id: UUID,
    document_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.document_file(db, str(delivery_boy_id), document_id, current["admin_id"], client_ip(request))


@router.put(
    "/{delivery_boy_id}/documents/{document_id}/review",
    summary="Verify or Reject a KYC Document",
    description="`status`: `verified` | `rejected`. `remarks` are required when rejecting and are shown to the partner.",
)
def review_document(
    delivery_boy_id: UUID,
    document_id: UUID,
    payload: AdminDocumentReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.review_document(
        db, str(delivery_boy_id), document_id, payload, current["admin_id"], client_ip(request)
    )


@router.put(
    "/{delivery_boy_id}/approve",
    summary="Approve Delivery Partner",
    description="Requires all four documents verified, vehicle details and payout details.",
)
def approve_delivery_boy(
    delivery_boy_id: UUID,
    request: Request,
    payload: Optional[AdminApprovalRequest] = None,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.set_approval(
        db, str(delivery_boy_id), approve=True, note=payload.note if payload else None,
        admin_id=current["admin_id"], ip=client_ip(request),
    )


@router.put(
    "/{delivery_boy_id}/reject",
    summary="Reject Delivery Partner",
    description="`note` is required and shown to the partner. Takes the partner offline and releases unpicked orders.",
)
def reject_delivery_boy(
    delivery_boy_id: UUID,
    payload: AdminApprovalRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.set_approval(
        db, str(delivery_boy_id), approve=False, note=payload.note,
        admin_id=current["admin_id"], ip=client_ip(request),
    )


@router.get(
    "/{delivery_boy_id}/payout-details",
    summary="Full Payout Details (for manual transfer)",
    description="Unmasked bank account for paying a withdrawal. Audited. **super_admin**.",
)
def get_payout_details(
    delivery_boy_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminDeliveryBoyService.payout_details(db, str(delivery_boy_id), current["admin_id"], client_ip(request))


@router.put(
    "/{delivery_boy_id}",
    summary="Update Delivery Partner",
    description=(
        "Name / vehicle corrections and `is_active`. Deactivating signs the partner out, takes them offline "
        "and releases orders they have not picked up yet."
    ),
)
def update_delivery_boy(
    delivery_boy_id: UUID,
    payload: AdminUpdateDeliveryBoyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.update_delivery_boy(
        db, str(delivery_boy_id), payload, current["admin_id"], client_ip(request)
    )


@router.get(
    "/{delivery_boy_id}/vendors",
    summary="Kitchens This Partner Serves",
    description=(
        "`assigned_vendors` (name, address, contact, kitchen status, open tasks), `assigned_vendor_count` and "
        "`vendor_history` (ended assignments)."
    ),
)
def list_vendors(delivery_boy_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminDeliveryBoyService.list_vendors(db, str(delivery_boy_id))


@router.post(
    "/{delivery_boy_id}/vendors",
    summary="Assign a Kitchen to the Partner",
    description=(
        "Adds the kitchen to the partner's kitchens (others are kept). A kitchen has one current partner: if it "
        "had another, it moves here, with every task that partner has not picked up yet. From now on the "
        "kitchen's new one-time orders, subscriptions and daily meals go to this partner automatically. "
        "Assigning the same kitchen again only fills tasks still missing a partner."
    ),
)
def add_vendor(
    delivery_boy_id: UUID,
    payload: AdminAssignVendorRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin),
):
    return AdminDeliveryBoyService.add_vendor(
        db, str(delivery_boy_id), payload.provider_id, current["admin_id"], note=payload.note, ip=client_ip(request),
    )


@router.delete(
    "/{delivery_boy_id}/vendors/{provider_id}",
    summary="Remove a Kitchen from the Partner",
    description=(
        "Only this kitchen is removed; the partner's other kitchens are untouched. Its tasks the partner has not "
        "picked up become unassigned (flagged for an admin); picked-up ones stay with the partner."
    ),
)
def remove_vendor(
    delivery_boy_id: UUID,
    provider_id: UUID,
    request: Request,
    payload: AdminRemoveVendorRequest | None = None,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin),
):
    return AdminDeliveryBoyService.remove_vendor(
        db, str(delivery_boy_id), provider_id, current["admin_id"],
        reason=payload.reason if payload else None, ip=client_ip(request),
    )


@router.put(
    "/{delivery_boy_id}/assign-provider",
    summary="Add a Kitchen (legacy)",
    description=(
        "Kept for older admin builds. `provider_id` adds that kitchen (same as POST .../vendors); without it every "
        "kitchen is removed (shared pool). Use the /vendors endpoints instead."
    ),
    deprecated=True,
)
def assign_provider(
    delivery_boy_id: UUID,
    request: Request,
    provider_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDeliveryBoyService.assign_provider(
        db, str(delivery_boy_id), str(provider_id) if provider_id else None, current["admin_id"], client_ip(request)
    )
