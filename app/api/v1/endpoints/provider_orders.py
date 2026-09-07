from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

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
from app.models.order_model import Order
from app.models.extra_order_model import ExtraOrder

router = APIRouter()


# ── Subscriptions ─────────────────────────────────────────

@router.get(
    "/subscriptions",
    response_model=ProviderSubscriptionListResponse,
    summary="List Customer Subscriptions",
    description=(
        "**Fetch all subscriptions where customers have chosen this provider's packages.**\n\n"
        "Filter by `status` (`active`, `paused`, `cancelled`, `expired`). "
        "Each entry shows the customer, packages, meal slot, and date range.\n\n"
        "**When to call:** On the provider dashboard to see the current subscriber base."
    )
)
def list_subscriptions(
    status: Optional[str] = Query(
        None,
        description="Filter by status: pending, active, paused, cancelled, expired"
    ),
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.list_subscriptions(
        db,
        vendor_id=current_provider["provider_id"],
        status=status
    )


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=ProviderSubscriptionDetailResponse,
    summary="Get Subscription Detail",
    description=(
        "**Fetch full details of a single customer subscription.**\n\n"
        "Returns customer info, packages subscribed, daily order schedule, "
        "meal slot, and financial summary.\n\n"
        "**When to call:** When the provider taps on a subscription from the list."
    )
)
def get_subscription_detail(
    subscription_id: str,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.get_subscription_detail(
        db,
        vendor_id=current_provider["provider_id"],
        subscription_id=subscription_id
    )


# ── Subscription Orders ───────────────────────────────────

@router.get(
    "/subscription-orders",
    response_model=SubscriptionOrderListResponse,
    summary="List Daily Subscription Orders",
    description=(
        "**Fetch the list of subscription-based orders for a specific date.**\n\n"
        "Defaults to today. Filter by `order_date` (YYYY-MM-DD) and/or `status`. "
        "Each order includes the customer's delivery address, meal slot, and current status.\n\n"
        "**When to call:** Every morning when the provider prepares meals. "
        "Use alongside `GET /provider/orders/food-summary` to know how much food to prepare."
    )
)
def list_subscription_orders(
    order_date: Optional[date] = Query(
        None,
        description="Filter by order date (YYYY-MM-DD)"
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by status: scheduled, preparing, out_for_delivery, delivered, skipped, cancelled"
    ),
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.list_subscription_orders(
        db,
        vendor_id=current_provider["provider_id"],
        order_date=order_date,
        status=status
    )


@router.put(
    "/subscription-orders/{order_id}/status",
    response_model=UpdateOrderStatusResponse,
    summary="Update Subscription Order Status",
    description=(
        "**Move a subscription order through its lifecycle.**\n\n"
        "Valid status transitions:\n"
        "- `scheduled` → `preparing` (provider starts cooking)\n"
        "- `preparing` → `out_for_delivery` (handed to delivery boy)\n"
        "- `out_for_delivery` → `delivered` (confirmed delivered)\n\n"
        "**When to call:** As the kitchen processes each order. "
        "Assign a delivery boy first with `PUT /subscription-orders/{id}/assign-delivery-boy`."
    )
)
def update_subscription_order_status(
    order_id: str,
    body: UpdateOrderStatusRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.update_subscription_order_status(
        db,
        vendor_id=current_provider["provider_id"],
        order_id=order_id,
        new_status=body.status
    )


# ── Extra Orders ──────────────────────────────────────────

@router.get(
    "/extra",
    response_model=ProviderExtraOrderListResponse,
    summary="List One-Time (Extra) Orders",
    description=(
        "**Fetch one-time orders placed by users (not part of a subscription).**\n\n"
        "Filter by `delivery_date` and/or `status`. "
        "These are on-demand orders that need to be fulfilled alongside subscription orders.\n\n"
        "**When to call:** On the provider's order management screen for same-day extra orders."
    )
)
def list_extra_orders(
    delivery_date: Optional[date] = Query(
        None,
        description="Filter by delivery date (YYYY-MM-DD)"
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by status: pending, confirmed, preparing, out_for_delivery, delivered, cancelled"
    ),
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.list_extra_orders(
        db,
        vendor_id=current_provider["provider_id"],
        delivery_date=delivery_date,
        status=status
    )


@router.put(
    "/extra/{order_id}/status",
    response_model=UpdateOrderStatusResponse,
    summary="Update Extra Order Status",
    description=(
        "**Move a one-time (extra) order through its lifecycle.**\n\n"
        "Valid status transitions: `pending` → `confirmed` → `preparing` → "
        "`out_for_delivery` → `delivered`.\n\n"
        "Confirm the order first (`confirmed`) before preparing. "
        "Assign a delivery boy before marking `out_for_delivery`."
    )
)
def update_extra_order_status(
    order_id: str,
    body: UpdateOrderStatusRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.update_extra_order_status(
        db,
        vendor_id=current_provider["provider_id"],
        order_id=order_id,
        new_status=body.status
    )


# ── Assign Delivery Boy ───────────────────────────────────

@router.put(
    "/subscription-orders/{order_id}/assign-delivery-boy",
    summary="Assign Delivery Boy to Subscription Order",
    description=(
        "**Assign a delivery boy to a subscription order before dispatching.**\n\n"
        "Pass the `delivery_boy_id` (UUID). The delivery boy must belong to this provider. "
        "After assignment, update the order status to `out_for_delivery`.\n\n"
        "**Flow:** `preparing` → assign delivery boy → `out_for_delivery`"
    )
)
def assign_delivery_boy_to_order(
    order_id: str,
    body: AssignDeliveryBoyRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    order = (
        db.query(Order)
        .filter(
            Order.order_id == order_id,
            Order.vendor_reference_id == current_provider["provider_id"]
        )
        .first()
    )
    if not order:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Order not found")

    order.delivery_boy_reference_id = body.delivery_boy_id

    # Let the delivery boy know a new drop landed on their list
    from app.repositories.delivery_boy_repository import DeliveryBoyRepository
    DeliveryBoyRepository.create_notification(
        db,
        body.delivery_boy_id,
        type="order_assigned",
        title="New delivery assigned",
        body=f"Subscription order for {order.order_date} ({order.meal_slot}) has been assigned to you.",
        data={"order_id": str(order.order_id), "kind": "subscription"},
        commit=False,
    )
    db.commit()

    return {
        "success": True,
        "message": "Delivery boy assigned to subscription order",
        "order_id": order_id,
        "delivery_boy_id": str(body.delivery_boy_id)
    }


@router.put(
    "/extra/{order_id}/assign-delivery-boy",
    summary="Assign Delivery Boy to Extra Order",
    description=(
        "**Assign a delivery boy to a one-time (extra) order before dispatching.**\n\n"
        "Pass the `delivery_boy_id` (UUID). After assignment, update status to `out_for_delivery`.\n\n"
        "**Flow:** `confirmed` / `preparing` → assign delivery boy → `out_for_delivery`"
    )
)
def assign_delivery_boy_to_extra_order(
    order_id: str,
    body: AssignDeliveryBoyRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    order = (
        db.query(ExtraOrder)
        .filter(
            ExtraOrder.extra_order_id == order_id,
            ExtraOrder.vendor_reference_id == current_provider["provider_id"]
        )
        .first()
    )
    if not order:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Extra order not found")

    order.delivery_boy_reference_id = body.delivery_boy_id

    from app.repositories.delivery_boy_repository import DeliveryBoyRepository
    DeliveryBoyRepository.create_notification(
        db,
        body.delivery_boy_id,
        type="order_assigned",
        title="New delivery assigned",
        body=f"Extra order for {order.delivery_date} ({order.meal_slot}) has been assigned to you.",
        data={"order_id": str(order.extra_order_id), "kind": "extra"},
        commit=False,
    )
    db.commit()

    return {
        "success": True,
        "message": "Delivery boy assigned to extra order",
        "order_id": order_id,
        "delivery_boy_id": str(body.delivery_boy_id)
    }


# ── Daily Food Calculator ─────────────────────────────────

@router.get(
    "/food-summary",
    response_model=DailyFoodSummaryResponse,
    summary="Daily Food Preparation Summary",
    description=(
        "**Calculate how much food to prepare for a given date and meal slot.**\n\n"
        "Returns a breakdown per package: total quantity needed across all active subscription "
        "and extra orders for that day. Defaults to today.\n\n"
        "**When to call:** Every morning before the kitchen starts cooking, "
        "or the night before for next-day planning.\n\n"
        "**Tip:** Filter by `meal_slot` (breakfast / lunch / dinner) to get slot-specific quantities."
    )
)
def get_daily_food_summary(
    summary_date: date = Query(
        default=None,
        description="Date to calculate food for (YYYY-MM-DD). Defaults to today."
    ),
    meal_slot: Optional[str] = Query(
        None,
        description="Filter by meal slot: breakfast, lunch, or dinner. Omit for all slots."
    ),
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    from datetime import date as date_cls
    return ProviderOrderService.get_daily_food_summary(
        db,
        vendor_id=current_provider["provider_id"],
        summary_date=summary_date or date_cls.today(),
        meal_slot=meal_slot
    )
