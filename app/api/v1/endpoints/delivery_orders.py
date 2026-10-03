from typing import Optional
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import limit_by_ip
from app.dependencies.auth_dependency import get_delivery_session, get_current_delivery_boy
from app.services.delivery_boy_order_service import DeliveryBoyOrderService
from app.schemas.delivery_boy_schema import (
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

@router.get("/profile", response_model=dict, summary="Get Delivery Boy Profile")
def get_profile(db: Session = Depends(get_db), current=Depends(get_delivery_session)):
    return DeliveryBoyOrderService.get_profile(db, current["delivery_boy_id"])


@router.put(
    "/profile",
    response_model=dict,
    summary="Update Delivery Boy Profile",
    description="Personal and vehicle details, and the online / offline duty switch (approved partners only).",
)
def update_profile(
    payload: UpdateDeliveryBoyProfileRequest,
    db: Session = Depends(get_db),
    current=Depends(get_delivery_session)
):
    return DeliveryBoyOrderService.update_profile(db, current["delivery_boy_id"], payload)


# ── Subscription meals ────────────────────────────────────

@router.get(
    "/orders",
    response_model=DeliverySubscriptionOrderListResponse,
    summary="My Assigned Subscription Meals",
    description="Defaults to today. Use `from_date` / `to_date` (max 31 days) for history.",
)
def list_orders(
    order_date: Optional[date] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    meal_slot: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.list_orders(
        db, current["delivery_boy_id"], order_date=order_date, meal_slot=meal_slot,
        status=status, from_date=from_date, to_date=to_date,
    )


@router.get("/orders/{order_id}", response_model=DeliverySubscriptionOrderDetailResponse, summary="Meal Detail")
def get_order_detail(order_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.get_order_detail(db, current["delivery_boy_id"], order_id)


@router.put(
    "/orders/{order_id}/pickup",
    response_model=OrderActionResponse,
    summary="Confirm Pickup (with kitchen pickup code)",
    description="On the delivery date, after the kitchen marked the meal preparing. Requires the 4-digit pickup code.",
    dependencies=[Depends(limit_by_ip("pickup", 60, 300))],
)
def pickup_order(order_id: UUID, payload: PickupRequest, db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.pickup_order(db, current["delivery_boy_id"], order_id, payload)


@router.put(
    "/orders/{order_id}/deliver",
    response_model=OrderActionResponse,
    summary="Complete Delivery (with customer code)",
    description="Requires the customer's 6-digit code. Locks after 5 wrong codes.",
    dependencies=[Depends(limit_by_ip("deliver", 60, 300))],
)
def deliver_order(order_id: UUID, payload: DeliverRequest, db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.deliver_order(db, current["delivery_boy_id"], order_id, payload)


# ── One-time orders ───────────────────────────────────────

@router.get(
    "/extra-orders",
    response_model=DeliveryExtraOrderListResponse,
    summary="My Assigned One-Time Orders",
    description="Defaults to today. Use `from_date` / `to_date` (max 31 days) for history.",
)
def list_extra_orders(
    delivery_date: Optional[date] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    meal_slot: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.list_extra_orders(
        db, current["delivery_boy_id"], delivery_date=delivery_date, meal_slot=meal_slot,
        status=status, from_date=from_date, to_date=to_date,
    )


@router.get("/extra-orders/{order_id}", response_model=DeliveryExtraOrderDetailResponse, summary="One-Time Order Detail")
def get_extra_order_detail(order_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.get_extra_order_detail(db, current["delivery_boy_id"], order_id)


@router.put(
    "/extra-orders/{order_id}/pickup",
    response_model=OrderActionResponse,
    summary="Confirm Pickup of a One-Time Order (with pickup code)",
    dependencies=[Depends(limit_by_ip("pickup", 60, 300))],
)
def pickup_extra_order(order_id: UUID, payload: PickupRequest, db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.pickup_extra_order(db, current["delivery_boy_id"], order_id, payload)


@router.put(
    "/extra-orders/{order_id}/deliver",
    response_model=OrderActionResponse,
    summary="Complete a One-Time Delivery (with customer code)",
    dependencies=[Depends(limit_by_ip("deliver", 60, 300))],
)
def deliver_extra_order(order_id: UUID, payload: DeliverRequest, db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.deliver_extra_order(db, current["delivery_boy_id"], order_id, payload)
