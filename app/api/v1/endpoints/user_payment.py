from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.payment_schema import PaymentResponse, PaymentListResponse
from app.services.payment_service import PaymentService

router = APIRouter()


@router.get(
    "",
    response_model=PaymentListResponse,
    summary="List My Payments",
    description="Wallet top-ups (internal wallet in this phase; no payment gateway).",
)
def list_my_payments(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return PaymentService.list_my_payments(db, current_user["user_id"])


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get Payment Detail",
)
def get_payment(payment_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return PaymentService.get_payment(db, current_user["user_id"], payment_id)
