from typing import Optional
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip, hit, limit_by_ip
from app.dependencies.auth_dependency import get_delivery_session, get_current_delivery_boy
from app.services.delivery_boy_order_service import DeliveryBoyOrderService
from app.schemas.delivery_boy_schema import (
    UpdateDeliveryBoyProfileRequest,
    DeliverySubscriptionOrderListResponse,
    DeliverySubscriptionOrderDetailResponse,
    DeliveryExtraOrderListResponse,
    DeliveryExtraOrderDetailResponse,
    PickupRequest,
    BulkPickupRequest,
    DeliveryFailedRequest,
    DeliverRequest,
    OrderActionResponse,
)

router = APIRouter()

# Code checks are throttled per client IP and per partner account; the
# durable per-order / per-day attempt limits live in the service.
_PICKUP_IP = limit_by_ip("pickup", 240, 300)
_DELIVER_IP = limit_by_ip("deliver", 60, 300)


def _throttle_partner(bucket: str, current: dict, limit: int) -> None:
    hit(bucket, str(current["delivery_boy_id"]), limit, 300)


# A partner may collect dozens of meals from one kitchen in a few minutes, so
# pickups get a higher ceiling; guessing is stopped by the durable limits.
_PICKUP_PER_PARTNER = 120
_DELIVER_PER_PARTNER = 30


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


# ── Dashboard ─────────────────────────────────────────────

@router.get(
    "/dashboard",
    summary="Partner Home: Today's Deliveries, Active and Next Delivery",
    description=(
        "Today's counts (`total` = pending + picked up + delivered; cancelled shown separately), the "
        "`active_delivery` (picked up / on the way), the `next_delivery` (earliest order still at a "
        "kitchen, today or a later day), every order of today and the number of assigned subscriptions."
    ),
)
def dashboard(db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.dashboard(db, current["delivery_boy_id"])


# ── Assigned subscriptions ────────────────────────────────

@router.get(
    "/subscriptions",
    summary="My Assigned Subscriptions",
    description=(
        "Subscriptions Orleeno assigned to this partner. `status` defaults to `current` (active and "
        "paused). Each row has today's / pending / completed counts for this partner's meals and "
        "the next meal. `search` matches the customer or kitchen name."
    ),
)
def list_subscriptions(
    status: Optional[str] = Query(None, description="current (default) | active | paused | cancelled | switched | expired"),
    search: Optional[str] = Query(None, max_length=60),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy),
):
    return DeliveryBoyOrderService.list_subscriptions(
        db, current["delivery_boy_id"], status=status, search=search, page=page, limit=limit,
    )


@router.get(
    "/subscriptions/{subscription_id}",
    summary="Assigned Subscription Detail",
    description=(
        "Customer, delivery address, kitchen, plan and this partner's meals of the subscription. "
        "Each meal has a `group` (today | upcoming | completed | cancelled | failed | missed) and "
        "`is_active` / `is_next` flags. 404 unless the subscription is assigned to this partner."
    ),
)
def get_subscription_detail(subscription_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.get_subscription_detail(db, current["delivery_boy_id"], subscription_id)


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
    summary="Verify Pickup (kitchen's daily code)",
    description=(
        "On the delivery date, once the kitchen is preparing the meal or marked it ready. Requires the "
        "kitchen's 6-digit pickup code for today. Wrong codes are counted: 5 per order lock it "
        "(423 `PICKUP_LOCKED`), 10 per partner per day block pickups (429). Status -> `picked_up`."
    ),
    dependencies=[Depends(_PICKUP_IP)],
)
def pickup_order(order_id: UUID, payload: PickupRequest, request: Request, db: Session = Depends(get_db),
                 current=Depends(get_current_delivery_boy)):
    _throttle_partner("pickup_partner", current, _PICKUP_PER_PARTNER)
    return DeliveryBoyOrderService.pickup(db, current["delivery_boy_id"], "subscription", order_id, payload, client_ip(request))


@router.put(
    "/orders/{order_id}/start-delivery",
    response_model=OrderActionResponse,
    summary="Start Delivery",
    description="After pickup: `picked_up` -> `out_for_delivery`. The customer is notified.",
)
def start_delivery(order_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.start_delivery(db, current["delivery_boy_id"], "subscription", order_id)


@router.put(
    "/orders/{order_id}/arrived",
    response_model=OrderActionResponse,
    summary="Reached Customer",
    description="Tells the customer the partner is at the door (once) so they can share the delivery code.",
)
def mark_arrived(order_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.mark_arrived(db, current["delivery_boy_id"], "subscription", order_id)


@router.put(
    "/orders/{order_id}/deliver",
    response_model=OrderActionResponse,
    summary="Verify Delivery (customer's code)",
    description="Requires the customer's 6-digit code for this order. Locks after 5 wrong codes.",
    dependencies=[Depends(_DELIVER_IP)],
)
def deliver_order(order_id: UUID, payload: DeliverRequest, request: Request, db: Session = Depends(get_db),
                  current=Depends(get_current_delivery_boy)):
    _throttle_partner("deliver_partner", current, _DELIVER_PER_PARTNER)
    return DeliveryBoyOrderService.deliver(db, current["delivery_boy_id"], "subscription", order_id, payload, client_ip(request))


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
    summary="Verify Pickup of a One-Time Order (kitchen's daily code)",
    dependencies=[Depends(_PICKUP_IP)],
)
def pickup_extra_order(order_id: UUID, payload: PickupRequest, request: Request, db: Session = Depends(get_db),
                       current=Depends(get_current_delivery_boy)):
    _throttle_partner("pickup_partner", current, _PICKUP_PER_PARTNER)
    return DeliveryBoyOrderService.pickup(db, current["delivery_boy_id"], "extra", order_id, payload, client_ip(request))


@router.put("/extra-orders/{order_id}/start-delivery", response_model=OrderActionResponse, summary="Start a One-Time Delivery")
def start_extra_delivery(order_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.start_delivery(db, current["delivery_boy_id"], "extra", order_id)


@router.put("/extra-orders/{order_id}/arrived", response_model=OrderActionResponse, summary="Reached Customer (One-Time)")
def mark_extra_arrived(order_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.mark_arrived(db, current["delivery_boy_id"], "extra", order_id)


@router.put(
    "/extra-orders/{order_id}/deliver",
    response_model=OrderActionResponse,
    summary="Verify a One-Time Delivery (customer's code)",
    dependencies=[Depends(_DELIVER_IP)],
)
def deliver_extra_order(order_id: UUID, payload: DeliverRequest, request: Request, db: Session = Depends(get_db),
                        current=Depends(get_current_delivery_boy)):
    _throttle_partner("deliver_partner", current, _DELIVER_PER_PARTNER)
    return DeliveryBoyOrderService.deliver(db, current["delivery_boy_id"], "extra", order_id, payload, client_ip(request))



@router.post(
    "/pickups/bulk",
    summary="Pick Up Everything Ready at a Kitchen",
    description=(
        "Enter the kitchen's pickup code once to collect all of today's orders assigned to you that are "
        "ready there (subscription and one-time). A wrong code counts once toward the daily limit."
    ),
    dependencies=[Depends(limit_by_ip("pickup_bulk", 30, 600))],
)
def pickup_all(
    payload: BulkPickupRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy),
):
    return DeliveryBoyOrderService.pickup_all(
        db, current["delivery_boy_id"], payload.provider_id, payload.pickup_code, client_ip(request)
    )



@router.put(
    "/orders/{order_id}/failed",
    response_model=OrderActionResponse,
    summary="Could Not Deliver (Subscription Meal)",
    description="After 'arrived' and the waiting time: customer not reachable, wrong address or refused.",
)
def fail_subscription_delivery(order_id: UUID, payload: DeliveryFailedRequest, request: Request,
                               db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.fail_delivery(
        db, current["delivery_boy_id"], "subscription", order_id, payload, client_ip(request)
    )


@router.put(
    "/extra-orders/{order_id}/failed",
    response_model=OrderActionResponse,
    summary="Could Not Deliver (One-Time Order)",
    description="After 'arrived' and the waiting time: customer not reachable, wrong address or refused.",
)
def fail_extra_delivery(order_id: UUID, payload: DeliveryFailedRequest, request: Request,
                        db: Session = Depends(get_db), current=Depends(get_current_delivery_boy)):
    return DeliveryBoyOrderService.fail_delivery(
        db, current["delivery_boy_id"], "extra", order_id, payload, client_ip(request)
    )
