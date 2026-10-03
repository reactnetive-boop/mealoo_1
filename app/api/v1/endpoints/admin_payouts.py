from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.schemas.admin_schema import AdminProcessPayoutRequest
from app.services.payout_service import PayoutService

router = APIRouter()


@router.get(
    "",
    summary="Withdrawal Requests",
    description="Kitchen and delivery partner withdrawal requests. Filter by `status` and `owner_type`.",
)
def list_requests(
    status: Optional[str] = Query(None, pattern="^(pending|paid|rejected)$"),
    owner_type: Optional[str] = Query(None, pattern="^(provider|delivery_boy)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return PayoutService.list_all(db, status, owner_type, page, limit)


@router.put(
    "/{request_id}",
    summary="Mark a Withdrawal Paid or Reject It",
    description=(
        "`paid`: after transferring the money manually, record the bank / UPI `payout_reference`. "
        "`rejected`: the held amount goes back to the wallet. Audited. **super_admin**."
    ),
)
def process_request(
    request_id: UUID,
    payload: AdminProcessPayoutRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return PayoutService.process(
        db, request_id,
        approve=payload.action == "paid",
        admin_id=current["admin_id"],
        admin_note=payload.admin_note,
        payout_reference=payload.payout_reference,
        ip=client_ip(request),
    )
