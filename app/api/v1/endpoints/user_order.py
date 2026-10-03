from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import limit_by_ip
from app.dependencies.auth_dependency import get_current_user
from app.schemas.extra_order_schema import (
    PlaceExtraOrderRequest,
    PlaceOrderResponse,
    ExtraOrderListResponse,
    ExtraOrderResponse,
)
from app.services.extra_order_service import ExtraOrderService

router = APIRouter()


@router.post(
    "/extra/quote",
    summary="Price a One-Time Order (no charge)",
    description="Server-side breakdown per package and the total the order would cost.",
    dependencies=[Depends(limit_by_ip("quote", 120, 60))],
)
def quote_extra_order(
    payload: PlaceExtraOrderRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return ExtraOrderService.quote(db, current_user["user_id"], payload)


@router.post(
    "/extra",
    response_model=PlaceOrderResponse,
    summary="Place a One-Time Extra Order",
    description=(
        "All packages must come from the same kitchen, be served in `meal_slot`, and be sold to "
        "the address pincode. `delivery_date` is a business-local (IST) date: today only before "
        "the slot cut-off, at most 9 days ahead. The wallet is debited once; send an "
        "`Idempotency-Key` header to make retries safe."
    ),
)
def place_extra_order(
    payload: PlaceExtraOrderRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=80),
):
    return ExtraOrderService.place_order(db, current_user["user_id"], payload, idempotency_key)


@router.get(
    "/extra",
    response_model=ExtraOrderListResponse,
    summary="List My Extra Orders",
)
def get_order_list(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return ExtraOrderService.get_order_list(db, current_user["user_id"])


@router.get(
    "/extra/{order_id}",
    response_model=ExtraOrderResponse,
    summary="Get Extra Order Detail",
)
def get_order(order_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return ExtraOrderService.get_order(db, current_user["user_id"], order_id)


@router.put(
    "/extra/{order_id}/cancel",
    summary="Cancel a One-Time Order",
    description="Allowed while the kitchen has not confirmed it and before the cut-off. Full refund.",
)
def cancel_order(order_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return ExtraOrderService.cancel_order(db, current_user["user_id"], order_id)
