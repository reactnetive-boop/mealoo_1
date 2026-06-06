from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from uuid import UUID

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.extra_order_schema import (
    PlaceExtraOrderRequest,
    PlaceOrderResponse,
    ExtraOrderListResponse,
    ExtraOrderResponse
)
from app.services.extra_order_service import ExtraOrderService

router = APIRouter()


@router.post(
    "/extra",
    response_model=PlaceOrderResponse
)
def place_extra_order(
    payload: PlaceExtraOrderRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ExtraOrderService.place_order(
        db,
        current_user["user_id"],
        payload
    )


@router.get(
    "/extra",
    response_model=ExtraOrderListResponse
)
def get_order_list(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ExtraOrderService.get_order_list(
        db,
        current_user["user_id"]
    )


@router.get(
    "/extra/{order_id}",
    response_model=ExtraOrderResponse
)
def get_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ExtraOrderService.get_order(
        db,
        current_user["user_id"],
        order_id
    )
