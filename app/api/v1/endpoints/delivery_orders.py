from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_delivery_boy
from app.services.delivery_boy_auth_service import DeliveryBoyAuthService
from app.services.delivery_boy_order_service import DeliveryBoyOrderService
from app.schemas.delivery_boy_schema import (
    DeliveryBoyProfileResponse,
    UpdateDeliveryBoyProfileRequest,
    DeliverySubscriptionOrderListResponse,
    DeliverySubscriptionOrderDetailResponse,
    DeliveryExtraOrderListResponse,
    DeliveryExtraOrderDetailResponse,
    PickupRequest,
    DeliverRequest,
    OrderActionResponse,
)

router = APIRouter()


# ── Profile ───────────────────────────────────────────────

@router.get("/profile", response_model=dict)
def get_profile(
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.get_profile(db, current["delivery_boy_id"])


@router.put("/profile", response_model=dict)
def update_profile(
    payload: UpdateDeliveryBoyProfileRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.update_profile(db, current["delivery_boy_id"], payload)


# ── Subscription Orders ───────────────────────────────────

@router.get(
    "/orders",
    response_model=DeliverySubscriptionOrderListResponse
)
def list_orders(
    order_date: Optional[date] = Query(
        None,
        description="Date to fetch orders for (YYYY-MM-DD). Defaults to today."
    ),
    meal_slot: Optional[str] = Query(
        None,
        description="Filter by meal slot: breakfast, lunch, or dinner"
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by status: scheduled, preparing, out_for_delivery, delivered, skipped, cancelled"
    ),
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.list_orders(
        db,
        delivery_boy_id=current["delivery_boy_id"],
        order_date=order_date,
        meal_slot=meal_slot,
        status=status
    )


@router.get(
    "/orders/{order_id}",
    response_model=DeliverySubscriptionOrderDetailResponse
)
def get_order_detail(
    order_id: str,
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.get_order_detail(
        db,
        delivery_boy_id=current["delivery_boy_id"],
        order_id=order_id
    )


@router.put(
    "/orders/{order_id}/pickup",
    response_model=OrderActionResponse
)
def pickup_order(
    order_id: str,
    payload: PickupRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.pickup_order(
        db,
        delivery_boy_id=current["delivery_boy_id"],
        order_id=order_id,
        payload=payload
    )


@router.put(
    "/orders/{order_id}/deliver",
    response_model=OrderActionResponse
)
def deliver_order(
    order_id: str,
    payload: DeliverRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.deliver_order(
        db,
        delivery_boy_id=current["delivery_boy_id"],
        order_id=order_id,
        payload=payload
    )


# ── Extra Orders ──────────────────────────────────────────

@router.get(
    "/extra-orders",
    response_model=DeliveryExtraOrderListResponse
)
def list_extra_orders(
    delivery_date: Optional[date] = Query(
        None,
        description="Date to fetch orders for (YYYY-MM-DD). Defaults to today."
    ),
    meal_slot: Optional[str] = Query(
        None,
        description="Filter by meal slot: breakfast, lunch, or dinner"
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by status: pending, confirmed, preparing, out_for_delivery, delivered, cancelled"
    ),
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.list_extra_orders(
        db,
        delivery_boy_id=current["delivery_boy_id"],
        delivery_date=delivery_date,
        meal_slot=meal_slot,
        status=status
    )


@router.get(
    "/extra-orders/{order_id}",
    response_model=DeliveryExtraOrderDetailResponse
)
def get_extra_order_detail(
    order_id: str,
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.get_extra_order_detail(
        db,
        delivery_boy_id=current["delivery_boy_id"],
        order_id=order_id
    )


@router.put(
    "/extra-orders/{order_id}/pickup",
    response_model=OrderActionResponse
)
def pickup_extra_order(
    order_id: str,
    payload: PickupRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.pickup_extra_order(
        db,
        delivery_boy_id=current["delivery_boy_id"],
        order_id=order_id,
        payload=payload
    )


@router.put(
    "/extra-orders/{order_id}/deliver",
    response_model=OrderActionResponse
)
def deliver_extra_order(
    order_id: str,
    payload: PickupRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.deliver_extra_order(
        db,
        delivery_boy_id=current["delivery_boy_id"],
        order_id=order_id,
        payload=payload
    )
