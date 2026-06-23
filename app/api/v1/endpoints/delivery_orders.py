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

@router.get(
    "/profile",
    response_model=dict,
    summary="Get Delivery Boy Profile",
    description=(
        "**Fetch the logged-in delivery boy's profile.**\n\n"
        "Returns name, mobile, assigned provider, and account status.\n\n"
        "**When to call:** On app launch after login, or when navigating to the profile screen."
    )
)
def get_profile(
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.get_profile(db, current["delivery_boy_id"])


@router.put(
    "/profile",
    response_model=dict,
    summary="Update Delivery Boy Profile",
    description=(
        "**Update the delivery boy's name or other profile details.**\n\n"
        "Only the fields provided will be updated."
    )
)
def update_profile(
    payload: UpdateDeliveryBoyProfileRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyOrderService.update_profile(db, current["delivery_boy_id"], payload)


# ── Subscription Orders ───────────────────────────────────

@router.get(
    "/orders",
    response_model=DeliverySubscriptionOrderListResponse,
    summary="List My Subscription Delivery Orders",
    description=(
        "**Fetch subscription orders assigned to this delivery boy.**\n\n"
        "Defaults to today's orders. Filter by `order_date`, `meal_slot` "
        "(breakfast / lunch / dinner), and/or `status`.\n\n"
        "**When to call:** When the delivery boy opens the app to see their daily delivery list. "
        "Refresh before each meal slot.\n\n"
        "**Flow:** Login → `GET /delivery/orders` → tap order → `GET /delivery/orders/{id}` → "
        "`PUT /delivery/orders/{id}/pickup` → `PUT /delivery/orders/{id}/deliver`"
    )
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
    response_model=DeliverySubscriptionOrderDetailResponse,
    summary="Get Subscription Order Detail",
    description=(
        "**Fetch full details of a specific subscription order.**\n\n"
        "Returns delivery address, customer name, package items, meal slot, OTP for delivery confirmation, "
        "and current status.\n\n"
        "**When to call:** When the delivery boy taps on an order from the list to navigate or confirm."
    )
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
    response_model=OrderActionResponse,
    summary="Pickup Subscription Order from Provider",
    description=(
        "**Mark a subscription order as picked up from the vendor's kitchen.**\n\n"
        "The provider must have set the order status to `out_for_delivery` first. "
        "Call this when the delivery boy picks up the food parcel.\n\n"
        "**Flow:** Provider sets `out_for_delivery` → delivery boy calls `PUT /orders/{id}/pickup` → "
        "`PUT /orders/{id}/deliver`"
    )
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
    response_model=OrderActionResponse,
    summary="Mark Subscription Order as Delivered",
    description=(
        "**Confirm that a subscription order has been delivered to the customer.**\n\n"
        "The customer's OTP may be required for confirmation (check `GET /orders/{id}` for the OTP field). "
        "This marks the order `delivered` and triggers the provider earnings credit.\n\n"
        "**When to call:** After handing the order to the customer at their door."
    )
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
    response_model=DeliveryExtraOrderListResponse,
    summary="List My Extra (One-Time) Delivery Orders",
    description=(
        "**Fetch one-time orders assigned to this delivery boy.**\n\n"
        "Filter by `delivery_date`, `meal_slot`, and/or `status`. "
        "These are separate from subscription orders and need to be delivered alongside them.\n\n"
        "**When to call:** Same time as `GET /delivery/orders` — check both lists each morning."
    )
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
    response_model=DeliveryExtraOrderDetailResponse,
    summary="Get Extra Order Detail",
    description=(
        "**Fetch full details of a specific one-time delivery order.**\n\n"
        "Returns delivery address, customer info, items, amount, and current status.\n\n"
        "**When to call:** When the delivery boy taps on an extra order to navigate to the address."
    )
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
    response_model=OrderActionResponse,
    summary="Pickup Extra Order from Provider",
    description=(
        "**Mark a one-time order as picked up from the vendor.**\n\n"
        "Call this when collecting the food parcel from the kitchen for an extra order.\n\n"
        "**Flow:** Provider marks `out_for_delivery` → `PUT /extra-orders/{id}/pickup` → "
        "`PUT /extra-orders/{id}/deliver`"
    )
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
    response_model=OrderActionResponse,
    summary="Mark Extra Order as Delivered",
    description=(
        "**Confirm that a one-time (extra) order has been delivered to the customer.**\n\n"
        "Call this after handing the parcel to the customer at their delivery address."
    )
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
