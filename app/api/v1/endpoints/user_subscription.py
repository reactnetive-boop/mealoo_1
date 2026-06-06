from fastapi import APIRouter, Depends, Query

from sqlalchemy.orm import Session

from uuid import UUID

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.subscription_schema import (
    SubscriptionPlanListResponse,
    CreateSubscriptionRequest,
    CreateSubscriptionResponse,
    SubscriptionListResponse,
    SubscriptionResponse,
    CancelSubscriptionRequest
)
from app.schemas.user_menu_schema import UserPackageListResponse
from app.services.subscription_service import SubscriptionService

router = APIRouter()


@router.get(
    "/plans",
    response_model=SubscriptionPlanListResponse
)
def list_subscription_plans(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.list_plans(db)


@router.get(
    "/packages"
)
def list_subscribable_packages(
    pin_code: int = Query(
        ...,
        description="Pincode to filter providers in your area"
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.list_subscribable_packages(
        db,
        pin_code
    )


@router.post(
    "",
    response_model=CreateSubscriptionResponse
)
def create_subscription(
    payload: CreateSubscriptionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.create_subscription(
        db,
        current_user["user_id"],
        payload
    )


@router.get(
    "",
    response_model=SubscriptionListResponse
)
def get_my_subscriptions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.get_my_subscriptions(
        db,
        current_user["user_id"]
    )


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionResponse
)
def get_subscription(
    subscription_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.get_subscription(
        db,
        current_user["user_id"],
        subscription_id
    )


@router.put(
    "/{subscription_id}/cancel"
)
def cancel_subscription(
    subscription_id: UUID,
    payload: CancelSubscriptionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.cancel_subscription(
        db,
        current_user["user_id"],
        subscription_id,
        payload
    )
