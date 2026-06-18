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
    response_model=ProviderSubscriptionListResponse
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
        vendor_id=current_provider.provider_id,
        status=status
    )


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=ProviderSubscriptionDetailResponse
)
def get_subscription_detail(
    subscription_id: str,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.get_subscription_detail(
        db,
        vendor_id=current_provider.provider_id,
        subscription_id=subscription_id
    )


# ── Subscription Orders ───────────────────────────────────

@router.get(
    "/subscription-orders",
    response_model=SubscriptionOrderListResponse
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
        vendor_id=current_provider.provider_id,
        order_date=order_date,
        status=status
    )


@router.put(
    "/subscription-orders/{order_id}/status",
    response_model=UpdateOrderStatusResponse
)
def update_subscription_order_status(
    order_id: str,
    body: UpdateOrderStatusRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.update_subscription_order_status(
        db,
        vendor_id=current_provider.provider_id,
        order_id=order_id,
        new_status=body.status
    )


# ── Extra Orders ──────────────────────────────────────────

@router.get(
    "/extra",
    response_model=ProviderExtraOrderListResponse
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
        vendor_id=current_provider.provider_id,
        delivery_date=delivery_date,
        status=status
    )


@router.put(
    "/extra/{order_id}/status",
    response_model=UpdateOrderStatusResponse
)
def update_extra_order_status(
    order_id: str,
    body: UpdateOrderStatusRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderOrderService.update_extra_order_status(
        db,
        vendor_id=current_provider.provider_id,
        order_id=order_id,
        new_status=body.status
    )


# ── Assign Delivery Boy ───────────────────────────────────

@router.put("/subscription-orders/{order_id}/assign-delivery-boy")
def assign_delivery_boy_to_order(
    order_id: str,
    body: AssignDeliveryBoyRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.vendor_id == current_provider.provider_id
        )
        .first()
    )
    if not order:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Order not found")

    order.delivery_boy_id = body.delivery_boy_id
    db.commit()

    return {
        "success": True,
        "message": "Delivery boy assigned to subscription order",
        "order_id": order_id,
        "delivery_boy_id": str(body.delivery_boy_id)
    }


@router.put("/extra/{order_id}/assign-delivery-boy")
def assign_delivery_boy_to_extra_order(
    order_id: str,
    body: AssignDeliveryBoyRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    order = (
        db.query(ExtraOrder)
        .filter(
            ExtraOrder.id == order_id,
            ExtraOrder.vendor_id == current_provider.provider_id
        )
        .first()
    )
    if not order:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Extra order not found")

    order.delivery_boy_id = body.delivery_boy_id
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
    response_model=DailyFoodSummaryResponse
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
        vendor_id=current_provider.provider_id,
        summary_date=summary_date or date_cls.today(),
        meal_slot=meal_slot
    )
