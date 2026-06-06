from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.wallet_schema import (
    WalletRechargeRequest,
    WalletRechargeResponse,
    WalletDetailsResponse,
    WalletTransactionListResponse
)
from app.services.wallet_service import WalletService

router = APIRouter()


@router.get(
    "",
    response_model=WalletDetailsResponse
)
def get_wallet_details(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return WalletService.get_wallet_details(
        db,
        current_user["user_id"]
    )


@router.get(
    "/transactions",
    response_model=WalletTransactionListResponse
)
def get_transaction_history(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return WalletService.get_transaction_history(
        db,
        current_user["user_id"]
    )


@router.post(
    "/recharge",
    response_model=WalletRechargeResponse
)
def recharge_wallet(
    payload: WalletRechargeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return WalletService.recharge(
        db,
        current_user["user_id"],
        payload
    )
