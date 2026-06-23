from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from uuid import UUID

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.extra_order_schema import (
    PlaceExtraOrderRequest,
    PlaceOrderResponse,
    ExtraOrderListResponse,
    ExtraOrderResponse
)
from app.services.extra_order_service import ExtraOrderService

router = APIRouter()


@router.post(
    "/extra",
    response_model=PlaceOrderResponse,
    summary="Place a One-Time Extra Order",
    description=(
        "**Order a meal once without a subscription.**\n\n"
        "This is for users who want to order on-demand rather than subscribing. "
        "Requires `package_id`, `vendor_id`, `address_id`, `meal_slot`, and `delivery_date`. "
        "Payment is deducted from the user's wallet.\n\n"
        "**Prerequisite:** Wallet must have sufficient balance (`GET /user/wallet`). "
        "Package must be available and active.\n\n"
        "**Flow:** Browse packages → check wallet balance → `POST /user/order/extra` → "
        "`GET /user/order/extra` to view order status"
    )
)
def place_extra_order(
    payload: PlaceExtraOrderRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ExtraOrderService.place_order(
        db,
        current_user["user_id"],
        payload
    )


@router.get(
    "/extra",
    response_model=ExtraOrderListResponse,
    summary="List My Extra Orders",
    description=(
        "**Fetch the complete history of one-time (extra) orders placed by the user.**\n\n"
        "Returns order status, delivery date, meal slot, package, and amount paid. "
        "Use `order_id` from this list to get full details.\n\n"
        "**When to call:** On the 'Order History' screen."
    )
)
def get_order_list(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ExtraOrderService.get_order_list(
        db,
        current_user["user_id"]
    )


@router.get(
    "/extra/{order_id}",
    response_model=ExtraOrderResponse,
    summary="Get Extra Order Detail",
    description=(
        "**Fetch full details of a specific one-time order.**\n\n"
        "Returns order status, delivery address, package items, amount, and timestamps. "
        "Use `order_id` from the `GET /user/order/extra` list response.\n\n"
        "**When to call:** When the user taps on an order in the history list."
    )
)
def get_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ExtraOrderService.get_order(
        db,
        current_user["user_id"],
        order_id
    )
