from typing import Optional
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.services.admin_order_service import AdminOrderService
from app.schemas.admin_schema import (
    AdminForceStatusRequest,
    AdminAssignDeliveryBoyRequest,
    AdminReassignProviderRequest,
    AdminAssignSubscriptionRequest,
    AdminUnassignSubscriptionRequest,
    AdminResetVerificationRequest,
)

router = APIRouter()


@router.get(
    "/subscriptions",
    summary="List All Subscriptions (Admin)",
    description=(
        "**Fetch a paginated list of all subscriptions across the platform.**\n\n"
        "Filter by `vendor_id`, `user_id`, `status`, `delivery_boy_id`, `assignment` "
        "(`assigned` / `unassigned`) and `search` (customer name or phone, kitchen name, subscription id prefix). "
        "Rows include customer, kitchen and delivery partner names.\n\n"
        "**When to call:** On the admin orders / subscriptions overview screen."
    )
)
def list_subscriptions(
    vendor_id: Optional[UUID] = Query(None),
    user_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    delivery_boy_id: Optional[UUID] = Query(None),
    assignment: Optional[str] = Query(None, description="assigned | unassigned"),
    search: Optional[str] = Query(None, max_length=80),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.list_subscriptions(
        db,
        vendor_id=str(vendor_id) if vendor_id else None,
        user_id=str(user_id) if user_id else None,
        status=status, page=page, limit=limit,
        delivery_boy_id=str(delivery_boy_id) if delivery_boy_id else None,
        assignment=assignment, search=search,
    )


@router.get(
    "/subscriptions/{subscription_id}",
    summary="Subscription Detail with Delivery Assignment (Admin)",
    description=(
        "Customer, kitchen, plan, address, packages, order counts (completed / pending / in progress / "
        "cancelled / skipped / missed / failed / assigned), the current delivery partner, the "
        "assignment status and history, and every meal of the subscription."
    ),
)
def get_subscription_detail(subscription_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminOrderService.get_subscription_detail(db, str(subscription_id))


@router.put(
    "/subscriptions/{subscription_id}/assign-delivery-boy",
    summary="Admin: Assign a Delivery Partner to a Whole Subscription",
    description=(
        "Gives every meal of the subscription that is still at the kitchen (today onwards: scheduled, "
        "preparing, ready for pickup) to `delivery_boy_id`, and every meal generated later. Meals already "
        "picked up stay with whoever carries them; delivered, skipped and cancelled meals are not touched. "
        "Also used to reassign. Atomic; the response says what was assigned and skipped. The partner must be "
        "active, approved and in the shared pool or dedicated to this kitchen; the subscription must be "
        "active or paused."
    ),
)
def assign_subscription_delivery_boy(
    subscription_id: UUID,
    payload: AdminAssignSubscriptionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin),
):
    return AdminOrderService.assign_subscription_delivery_boy(
        db, str(subscription_id), payload, current["admin_id"], client_ip(request)
    )


@router.put(
    "/subscriptions/{subscription_id}/unassign-delivery-boy",
    summary="Admin: Remove the Subscription's Delivery Partner",
    description="Open meals at the kitchen become unassigned; meals already picked up stay with the partner.",
)
def unassign_subscription_delivery_boy(
    subscription_id: UUID,
    payload: AdminUnassignSubscriptionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin),
):
    return AdminOrderService.unassign_subscription_delivery_boy(
        db, str(subscription_id), payload, current["admin_id"], client_ip(request)
    )


@router.get(
    "/subscription-orders",
    summary="List Subscription Orders (Admin)",
    description=(
        "**Fetch daily subscription orders across all vendors.**\n\n"
        "Filter by `vendor_id`, `user_id`, `order_date` (YYYY-MM-DD), and/or `status`. "
        "Use for operations monitoring: track how many orders are in each status for today.\n\n"
        "**When to call:** On the admin real-time order tracking screen."
    )
)
def list_subscription_orders(
    vendor_id: Optional[UUID] = Query(None),
    user_id: Optional[UUID] = Query(None),
    order_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    delivery_boy_id: Optional[UUID] = Query(None),
    assignment: Optional[str] = Query(None, pattern="^(assigned|unassigned)$"),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.list_subscription_orders(
        db,
        vendor_id=str(vendor_id) if vendor_id else None,
        user_id=str(user_id) if user_id else None,
        order_date=order_date, status=status, page=page, limit=limit,
        delivery_boy_id=str(delivery_boy_id) if delivery_boy_id else None, assignment=assignment
    )


@router.put(
    "/subscription-orders/{order_id}/assign-delivery-boy",
    summary="Admin: Assign Delivery Boy to Order",
    description=(
        "**Manually assign or reassign a delivery boy to a subscription order.**\n\n"
        "Use when the provider hasn't assigned one, or when reassignment is needed due to delivery issues. "
        "Send `delivery_boy_id` in the request body."
    )
)
def assign_delivery_boy_to_order(
    order_id: UUID,
    payload: AdminAssignDeliveryBoyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.assign_delivery_boy(db, str(order_id), payload, current["admin_id"], client_ip(request))


@router.put(
    "/subscription-orders/{order_id}/reset-verification",
    summary="Admin: Unlock Pickup / Delivery Code Attempts",
    description="Clears the wrong-code counters of a locked meal after support has checked with the partner. Audited.",
)
def reset_order_verification(
    order_id: UUID,
    payload: AdminResetVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin),
):
    return AdminOrderService.reset_verification(db, "subscription", str(order_id), payload, current["admin_id"], client_ip(request))


@router.put(
    "/subscription-orders/{order_id}/reassign-provider",
    summary="Admin: Reassign Subscription Order to Another Provider",
    description=(
        "**Move a subscription order to a different provider.**\n\n"
        "Use in emergency situations when the original provider cannot fulfill the order "
        "(kitchen holiday). The current kitchen must be marked unavailable for the date; the new kitchen must be "
        "approved, open, serve the customer's pincode and have room. Allowed until the meal's cut-off. "
        "Send `new_provider_id`."
    )
)
def reassign_subscription_order_provider(
    order_id: UUID,
    payload: AdminReassignProviderRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.reassign_provider(db, str(order_id), payload, current["admin_id"], client_ip(request))


@router.put(
    "/subscription-orders/{order_id}/status",
    summary="Admin: Force Update Subscription Order Status",
    description=(
        "**Correct a stuck subscription meal.** Only transitions the order state machine allows for admins. "
        "`delivered` settles the kitchen / partner / platform money once; `cancelled` refunds the customer once. "
        "`reason` is required and audited.\n\n"
        "**Requires:** `super_admin` role."
    )
)
def force_update_order_status(
    order_id: UUID,
    payload: AdminForceStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminOrderService.force_update_order_status(db, str(order_id), payload, current["admin_id"], client_ip(request))


@router.get(
    "/extra-orders",
    summary="List Extra (One-Time) Orders (Admin)",
    description=(
        "**Fetch a paginated list of all one-time orders across the platform.**\n\n"
        "Filter by `vendor_id`, `user_id`, `delivery_date`, and/or `status`. "
        "Use to monitor on-demand order fulfillment."
    )
)
def list_extra_orders(
    vendor_id: Optional[UUID] = Query(None),
    user_id: Optional[UUID] = Query(None),
    delivery_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    delivery_boy_id: Optional[UUID] = Query(None),
    assignment: Optional[str] = Query(None, pattern="^(assigned|unassigned)$"),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.list_extra_orders(
        db,
        vendor_id=str(vendor_id) if vendor_id else None,
        user_id=str(user_id) if user_id else None,
        delivery_date=delivery_date, status=status, page=page, limit=limit,
        delivery_boy_id=str(delivery_boy_id) if delivery_boy_id else None, assignment=assignment
    )


@router.put(
    "/extra-orders/{order_id}/assign-delivery-boy",
    summary="Admin: Assign Delivery Boy to Extra Order",
    description=(
        "**Manually assign or reassign a delivery boy to a one-time order.**\n\n"
        "Use when the provider hasn't assigned one or reassignment is needed. "
        "Send `delivery_boy_id` in the request body."
    )
)
def assign_delivery_boy_to_extra_order(
    order_id: UUID,
    payload: AdminAssignDeliveryBoyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.assign_extra_delivery_boy(db, str(order_id), payload, current["admin_id"], client_ip(request))


@router.put(
    "/extra-orders/{order_id}/reset-verification",
    summary="Admin: Unlock Pickup / Delivery Code Attempts (One-Time Order)",
)
def reset_extra_order_verification(
    order_id: UUID,
    payload: AdminResetVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin),
):
    return AdminOrderService.reset_verification(db, "extra", str(order_id), payload, current["admin_id"], client_ip(request))


@router.put(
    "/extra-orders/{order_id}/reassign-provider",
    summary="Admin: Reassign Extra Order to Another Provider",
    description=(
        "**Move a one-time order to a different provider.**\n\n"
        "Same rules as subscription meals; the new kitchen confirms the order again. Send `new_provider_id`."
    )
)
def reassign_extra_order_provider(
    order_id: UUID,
    payload: AdminReassignProviderRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminOrderService.reassign_extra_order_provider(db, str(order_id), payload, current["admin_id"], client_ip(request))


@router.put(
    "/extra-orders/{order_id}/status",
    summary="Admin: Force Update Extra Order Status",
    description=(
        "**Correct a stuck one-time order.** Same rules as subscription meals: `delivered` settles once, "
        "`cancelled` refunds once, `reason` is required and audited.\n\n"
        "**Requires:** `super_admin` role."
    )
)
def force_update_extra_order_status(
    order_id: UUID,
    payload: AdminForceStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminOrderService.force_update_extra_order_status(db, str(order_id), payload, current["admin_id"], client_ip(request))
