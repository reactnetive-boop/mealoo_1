from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.schemas.payment_schema import PaymentListResponse, PaymentResponse, RefundPaymentRequest
from app.services.admin_payment_service import AdminPaymentService

router = APIRouter()


@router.get(
    "",
    response_model=PaymentListResponse,
    summary="List All Payments",
    description=(
        "**Fetch a paginated list of all payments across the platform.**\n\n"
        "Filter by `status` (`pending`, `completed`, `failed`, `refunded`) and/or "
        "`method` (`wallet`, `upi`, `card`, `netbanking`, `cash`).\n\n"
        "**When to call:** On the admin payments / financial reconciliation screen."
    )
)
def list_payments(
    status: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPaymentService.list_payments(db, status=status, method=method, page=page, limit=limit)


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get Payment Detail",
    description=(
        "**Fetch full details of a specific payment, including gateway response data.**\n\n"
        "Use `payment_id` from the payments list."
    )
)
def get_payment(
    payment_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPaymentService.get_payment(db, payment_id)


@router.put(
    "/{payment_id}/refund",
    summary="Refund a Payment",
    description=(
        "**Refund a completed payment and debit the amount back out of the user's wallet.**\n\n"
        "Optionally specify a partial `refund_amount`; defaults to the full payment amount. "
        "The wallet debit is clamped to the user's current balance if it's lower than the refund amount.\n\n"
        "**Requires:** `super_admin` role."
    )
)
def refund_payment(
    payment_id: UUID,
    payload: RefundPaymentRequest,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminPaymentService.refund_payment(db, payment_id, payload)
