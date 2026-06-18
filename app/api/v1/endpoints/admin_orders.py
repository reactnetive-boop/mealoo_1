from typing import Optional
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_order_service import AdminOrderService
from app.schemas.admin_schema import AdminForceStatusRequest, AdminAssignDeliveryBoyRequest, AdminReassignProviderRequest

router = APIRouter()


@router.get("/subscriptions")
def list_subscriptions(
    vendor_id: Optional[UUID] = Query(None),
    user_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.list_subscriptions(
        db,
        vendor_id=str(vendor_id) if vendor_id else None,
        user_id=str(user_id) if user_id else None,
        status=status, page=page, limit=limit
    )


@router.get("/subscription-orders")
def list_subscription_orders(
    vendor_id: Optional[UUID] = Query(None),
    user_id: Optional[UUID] = Query(None),
    order_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.list_subscription_orders(
        db,
        vendor_id=str(vendor_id) if vendor_id else None,
        user_id=str(user_id) if user_id else None,
        order_date=order_date, status=status, page=page, limit=limit
    )


@router.put("/subscription-orders/{order_id}/assign-delivery-boy")
def assign_delivery_boy_to_order(
    order_id: UUID,
    payload: AdminAssignDeliveryBoyRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.assign_delivery_boy(db, str(order_id), payload)


@router.put("/subscription-orders/{order_id}/reassign-provider")
def reassign_subscription_order_provider(
    order_id: UUID,
    payload: AdminReassignProviderRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.reassign_provider(db, str(order_id), payload)


@router.put("/subscription-orders/{order_id}/status")
def force_update_order_status(
    order_id: UUID,
    payload: AdminForceStatusRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.force_update_order_status(db, str(order_id), payload)


@router.get("/extra-orders")
def list_extra_orders(
    vendor_id: Optional[UUID] = Query(None),
    user_id: Optional[UUID] = Query(None),
    delivery_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.list_extra_orders(
        db,
        vendor_id=str(vendor_id) if vendor_id else None,
        user_id=str(user_id) if user_id else None,
        delivery_date=delivery_date, status=status, page=page, limit=limit
    )


@router.put("/extra-orders/{order_id}/assign-delivery-boy")
def assign_delivery_boy_to_extra_order(
    order_id: UUID,
    payload: AdminAssignDeliveryBoyRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.assign_extra_delivery_boy(db, str(order_id), payload)


@router.put("/extra-orders/{order_id}/reassign-provider")
def reassign_extra_order_provider(
    order_id: UUID,
    payload: AdminReassignProviderRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.reassign_extra_order_provider(db, str(order_id), payload)


@router.put("/extra-orders/{order_id}/status")
def force_update_extra_order_status(
    order_id: UUID,
    payload: AdminForceStatusRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.force_update_extra_order_status(db, str(order_id), payload)
