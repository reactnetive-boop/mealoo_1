from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.payment_schema import (
    InitiatePaymentRequest,
    InitiatePaymentResponse,
    ConfirmPaymentRequest,
    ConfirmPaymentResponse,
    PaymentResponse,
    PaymentListResponse
)
from app.services.payment_service import PaymentService

router = APIRouter()


@router.post(
    "/initiate",
    response_model=InitiatePaymentResponse,
    summary="Initiate Wallet Top-up Payment",
    description=(
        "**Start a wallet recharge via the payment gateway.**\n\n"
        "Creates a `pending` payment and returns a `gateway_order_id` for the client "
        "to hand to the payment gateway SDK. No money moves yet.\n\n"
        "**Flow:** `POST /user/payment/initiate` → pay via gateway SDK using `gateway_order_id` → "
        "`POST /user/payment/{payment_id}/confirm`"
    )
)
def initiate_payment(
    payload: InitiatePaymentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return PaymentService.initiate_topup(
        db,
        current_user["user_id"],
        payload.amount
    )


@router.post(
    "/{payment_id}/confirm",
    response_model=ConfirmPaymentResponse,
    summary="Confirm Wallet Top-up Payment",
    description=(
        "**Confirm a pending payment and credit the wallet.**\n\n"
        "Call after the payment gateway SDK reports success, passing the `gateway_txn_id` it returned. "
        "Credits the wallet by the payment amount and marks the payment `completed`.\n\n"
        "**When to call:** Immediately after the gateway SDK's success callback."
    )
)
def confirm_payment(
    payment_id: UUID,
    payload: ConfirmPaymentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return PaymentService.confirm_topup(
        db,
        current_user["user_id"],
        payment_id,
        payload.gateway_txn_id
    )


@router.get(
    "",
    response_model=PaymentListResponse,
    summary="List My Payments",
    description=(
        "**Fetch all payments made by the logged-in user.**\n\n"
        "**When to call:** On the payment / billing history screen."
    )
)
def list_my_payments(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return PaymentService.list_my_payments(db, current_user["user_id"])


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get Payment Detail",
    description=(
        "**Fetch full details of a specific payment.**\n\n"
        "Use `payment_id` from `GET /user/payment`."
    )
)
def get_payment(
    payment_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return PaymentService.get_payment(db, current_user["user_id"], payment_id)
