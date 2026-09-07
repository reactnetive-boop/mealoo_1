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
    response_model=ProviderWalletDetailsResponse,
    summary="Get Provider Wallet Balance",
    description=(
        "**Fetch the provider's earnings wallet balance.**\n\n"
        "Shows total earned, total withdrawn, and current available balance. "
        "Earnings are credited automatically as orders are delivered.\n\n"
        "**When to call:** On the provider's earnings/wallet dashboard screen."
    )
)
def get_wallet_details(
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderWalletService.get_wallet_details(
        db,
        provider_id=current_provider["provider_id"]
    )


@router.get(
    "/transactions",
    response_model=ProviderWalletTransactionListResponse,
    summary="Provider Wallet Transaction History",
    description=(
        "**Fetch credit and debit transactions for the provider's earnings wallet.**\n\n"
        "Filter by `type`: `credit` (deliveries paid out) or `debit` (withdrawals). "
        "Use this to show the earnings history on the wallet screen.\n\n"
        "**When to call:** When the provider navigates to 'Earnings History'."
    )
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
        provider_id=current_provider["provider_id"],
        txn_type=type
    )


@router.post(
    "/withdraw",
    response_model=WithdrawalResponse,
    summary="Request Earnings Withdrawal",
    description=(
        "**Request a withdrawal of available earnings to a bank account.**\n\n"
        "Send the `amount` to withdraw. The system validates sufficient available balance. "
        "Withdrawals are processed by the admin team.\n\n"
        "**When to call:** When the provider wants to transfer earnings to their bank account. "
        "Check balance first with `GET /provider/wallet`."
    )
)
def request_withdrawal(
    payload: WithdrawalRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderWalletService.withdraw(
        db,
        provider_id=current_provider["provider_id"],
        payload=payload
    )
