from typing import Optional
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_provider
from app.services.provider_order_service import ProviderOrderService
from app.schemas.provider_order_schema import (
    ProviderSubscriptionListResponse,
    ProviderSubscriptionDetailResponse,
    SubscriptionOrderListResponse,
    UpdateOrderStatusRequest,
    UpdateOrderStatusResponse,
    ProviderExtraOrderListResponse,
    DailyFoodSummaryResponse,
)
from app.schemas.delivery_boy_schema import AssignDeliveryBoyRequest

router = APIRouter()


@router.get(
    "/subscriptions",
    response_model=ProviderSubscriptionListResponse,
    summary="List Subscriptions with this Kitchen",
)
def list_subscriptions(
    status: Optional[str] = Query(None, description="active | paused | cancelled | switched | expired"),
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.list_subscriptions(db, vendor_id=current_provider["provider_id"], status=status)


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=ProviderSubscriptionDetailResponse,
    summary="Subscription Detail with Daily Meals",
)
def get_subscription_detail(
    subscription_id: UUID,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.get_subscription_detail(
        db, vendor_id=current_provider["provider_id"], subscription_id=subscription_id
    )


@router.get(
    "/subscription-orders",
    response_model=SubscriptionOrderListResponse,
    summary="List Subscription Meals",
    description=(
        "Defaults to today's meals (business date). Pass `order_date`, or `from_date` / "
        "`to_date`, for other days. The customer's delivery code is never included; "
        "`pickup_code` is what the kitchen gives the delivery partner at hand-over."
    ),
)
def list_subscription_orders(
    order_date: Optional[date] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    meal_slot: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.list_subscription_orders(
        db,
        vendor_id=current_provider["provider_id"],
        order_date=order_date,
        status=status,
        from_date=from_date,
        to_date=to_date,
        meal_slot=meal_slot,
    )


@router.put(
    "/subscription-orders/{order_id}/status",
    response_model=UpdateOrderStatusResponse,
    summary="Mark a Meal as Preparing",
    description=(
        "The only status a kitchen sets on a subscription meal is `preparing` (from `scheduled`, "
        "on the meal's date). Pickup and delivery are recorded by the delivery partner."
    ),
)
def update_subscription_order_status(
    order_id: UUID,
    body: UpdateOrderStatusRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.update_subscription_order_status(
        db, vendor_id=current_provider["provider_id"], order_id=order_id, new_status=body.status
    )


@router.get(
    "/extra",
    response_model=ProviderExtraOrderListResponse,
    summary="List One-Time Orders",
    description="Defaults to today and upcoming dates.",
)
def list_extra_orders(
    delivery_date: Optional[date] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.list_extra_orders(
        db,
        vendor_id=current_provider["provider_id"],
        delivery_date=delivery_date,
        status=status,
        from_date=from_date,
        to_date=to_date,
    )


@router.put(
    "/extra/{order_id}/status",
    response_model=UpdateOrderStatusResponse,
    summary="Confirm, Prepare or Decline a One-Time Order",
    description=(
        "Allowed: pending → confirmed, confirmed → preparing (on the delivery date), "
        "pending → cancelled (declined; the customer is refunded in full)."
    ),
)
def update_extra_order_status(
    order_id: UUID,
    body: UpdateOrderStatusRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.update_extra_order_status(
        db, vendor_id=current_provider["provider_id"], order_id=order_id, new_status=body.status
    )


@router.put(
    "/subscription-orders/{order_id}/assign-delivery-boy",
    summary="Assign Delivery Partner to a Meal",
    description="Partner must be approved, active, online and attached to this kitchen or the shared pool.",
)
def assign_delivery_boy_to_order(
    order_id: UUID,
    body: AssignDeliveryBoyRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.assign_delivery_boy(
        db, current_provider["provider_id"], "subscription", order_id, body.delivery_boy_id
    )


@router.put(
    "/extra/{order_id}/assign-delivery-boy",
    summary="Assign Delivery Partner to a One-Time Order",
)
def assign_delivery_boy_to_extra_order(
    order_id: UUID,
    body: AssignDeliveryBoyRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.assign_delivery_boy(
        db, current_provider["provider_id"], "extra", order_id, body.delivery_boy_id
    )


@router.get(
    "/food-summary",
    response_model=DailyFoodSummaryResponse,
    summary="What to Cook",
    description="Item totals for a date (defaults to today) and optional meal slot.",
)
def get_daily_food_summary(
    summary_date: Optional[date] = Query(None),
    meal_slot: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.get_daily_food_summary(
        db,
        vendor_id=current_provider["provider_id"],
        summary_date=summary_date or today_local(),
        meal_slot=meal_slot,
    )
