"""Admin tools: audit log, menu categories, admin accounts, broadcasts, partner wallet."""

from datetime import date
from typing import Literal, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip, limit_by_ip
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.domain import partner_leave
from app.schemas.delivery_boy_schema import LeaveRequest
from app.schemas.admin_schema import (
    AdminAccountCreateRequest,
    AdminAccountUpdateRequest,
    AdminBroadcastRequest,
    AdminCategoryCreateRequest,
    AdminCategoryUpdateRequest,
    AdminWalletAdjustRequest,
)
from app.services.admin_tools_service import (
    AdminAccountService,
    AuditLogService,
    BroadcastService,
    CategoryAdminService,
    PartnerWalletAdminService,
)

router = APIRouter()


# ── Audit log ─────────────────────────────────────────────────

@router.get(
    "/audit-logs",
    tags=["Admin — Audit Log"],
    summary="Search the Audit Log",
    description="Every recorded change: money actions, approvals, assignments, code verifications, reveals of "
                "bank details. Filter by table, record, actor, operation and date. **super_admin**.",
)
def search_audit_logs(
    table: Optional[str] = Query(None, max_length=100),
    record_id: Optional[UUID] = Query(None),
    actor_id: Optional[UUID] = Query(None),
    actor_type: Optional[str] = Query(None, max_length=30),
    operation: Optional[Literal["I", "U", "D"]] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current=Depends(require_super_admin),
):
    return AuditLogService.search(
        db, table=table, record_id=record_id, actor_id=actor_id, actor_type=actor_type, operation=operation,
        date_from=date_from, date_to=date_to, page=page, limit=limit,
    )


@router.get("/audit-logs/tables", tags=["Admin — Audit Log"], summary="Audited Tables (for the filter)")
def audit_tables(db: Session = Depends(get_db), current=Depends(require_super_admin)):
    return AuditLogService.tables(db)


# ── Menu categories ───────────────────────────────────────────

@router.get("/categories", tags=["Admin — Categories"], summary="All Menu Categories (incl. inactive)")
def list_categories(db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return CategoryAdminService.list(db)


@router.post("/categories", tags=["Admin — Categories"], summary="Create a Menu Category")
def create_category(payload: AdminCategoryCreateRequest, request: Request, db: Session = Depends(get_db),
                    current=Depends(require_super_admin)):
    return CategoryAdminService.create(db, payload, current["admin_id"], client_ip(request))


@router.put(
    "/categories/{category_id}",
    tags=["Admin — Categories"],
    summary="Edit / Hide a Menu Category",
    description="`is_active=false` hides it; refused while packages still use it.",
)
def update_category(category_id: UUID, payload: AdminCategoryUpdateRequest, request: Request,
                    db: Session = Depends(get_db), current=Depends(require_super_admin)):
    return CategoryAdminService.update(db, category_id, payload, current["admin_id"], client_ip(request))


# ── Admin accounts ────────────────────────────────────────────

@router.get("/admins", tags=["Admin — Accounts"], summary="Admin Accounts")
def list_admins(db: Session = Depends(get_db), current=Depends(require_super_admin)):
    return AdminAccountService.list(db)


@router.post("/admins", tags=["Admin — Accounts"], summary="Create an Admin Account")
def create_admin(payload: AdminAccountCreateRequest, request: Request, db: Session = Depends(get_db),
                 current=Depends(require_super_admin)):
    return AdminAccountService.create(db, payload, current["admin_id"], client_ip(request))


@router.put(
    "/admins/{admin_id}",
    tags=["Admin — Accounts"],
    summary="Change Role / Disable an Admin",
    description="A role change or deactivation signs that admin out. At least one active super_admin always remains.",
)
def update_admin(admin_id: UUID, payload: AdminAccountUpdateRequest, request: Request,
                 db: Session = Depends(get_db), current=Depends(require_super_admin)):
    return AdminAccountService.update(db, admin_id, payload, current["admin_id"], client_ip(request))


# ── Broadcast ─────────────────────────────────────────────────

@router.post(
    "/notifications/broadcast",
    tags=["Admin — Notifications"],
    summary="Send an Announcement",
    description="In-app notification (and push) to every active customer, kitchen, partner or everyone. "
                "Audited. **super_admin**.",
    dependencies=[Depends(limit_by_ip("admin_broadcast", 10, 3600))],
)
def broadcast(payload: AdminBroadcastRequest, request: Request, db: Session = Depends(get_db),
              current=Depends(require_super_admin)):
    return BroadcastService.send(db, payload, current["admin_id"], client_ip(request))


# ── Delivery partner wallet ───────────────────────────────────

@router.post(
    "/delivery-boys/{delivery_boy_id}/wallet/adjust",
    tags=["Admin — Delivery Boys"],
    summary="Manually Adjust a Partner Wallet",
    description="Credit or debit with a mandatory `reason`; recorded in the partner and platform ledgers and the "
                "audit log. Send an `Idempotency-Key` header so a retry is applied once. **super_admin**.",
)
def adjust_partner_wallet(
    delivery_boy_id: UUID,
    payload: AdminWalletAdjustRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=100),
    db: Session = Depends(get_db),
    current=Depends(require_super_admin),
):
    return PartnerWalletAdminService.adjust(
        db, delivery_boy_id, payload, current["admin_id"], idempotency_key or str(uuid4()), client_ip(request)
    )



# ── Delivery partner leave ────────────────────────────────────

@router.get("/delivery-boys/{delivery_boy_id}/leaves", tags=["Admin — Delivery Boys"], summary="Partner Leave Days")
def partner_leaves(delivery_boy_id: UUID, include_past: bool = Query(False), db: Session = Depends(get_db),
                   current=Depends(get_current_admin)):
    return partner_leave.list_leaves(db, delivery_boy_id, include_past=include_past)


@router.post(
    "/delivery-boys/{delivery_boy_id}/leaves",
    tags=["Admin — Delivery Boys"],
    summary="Mark a Partner on Leave",
    description="E.g. the partner called in sick. That day's deliveries are released for reassignment.",
)
def add_partner_leave(delivery_boy_id: UUID, payload: LeaveRequest, db: Session = Depends(get_db),
                      current=Depends(get_current_admin)):
    return partner_leave.add_leave(db, delivery_boy_id, payload.leave_date, payload.reason, "admin")


@router.delete("/delivery-boys/{delivery_boy_id}/leaves/{leave_date}", tags=["Admin — Delivery Boys"],
               summary="Cancel a Partner's Leave")
def cancel_partner_leave(delivery_boy_id: UUID, leave_date: date, db: Session = Depends(get_db),
                         current=Depends(get_current_admin)):
    return partner_leave.cancel_leave(db, delivery_boy_id, leave_date)
