from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_provider
from app.services.provider_wallet_service import ProviderWalletService
from app.schemas.provider_wallet_schema import (
    ProviderWalletDetailsResponse,
    ProviderWalletTransactionListResponse,
    WithdrawalRequest,
    WithdrawalResponse,
)

router = APIRouter()


@router.get(
    "",
    response_model=ProviderWalletDetailsResponse
)
def get_wallet_details(
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderWalletService.get_wallet_details(
        db,
        provider_id=current_provider.provider_id
    )


@router.get(
    "/transactions",
    response_model=ProviderWalletTransactionListResponse
)
def get_transaction_history(
    type: Optional[str] = Query(
        None,
        description="Filter by type: credit or debit"
    ),
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderWalletService.get_transaction_history(
        db,
        provider_id=current_provider.provider_id,
        txn_type=type
    )


@router.post(
    "/withdraw",
    response_model=WithdrawalResponse
)
def request_withdrawal(
    payload: WithdrawalRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderWalletService.withdraw(
        db,
        provider_id=current_provider.provider_id,
        payload=payload
    )
