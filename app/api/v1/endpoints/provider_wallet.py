from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_active_provider as get_current_provider
from app.services.provider_wallet_service import ProviderWalletService
from app.services.payout_details_service import PayoutDetailsService
from app.schemas.payout_schema import PayoutDetailsRequest
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
    summary="Request a Withdrawal",
    description=(
        "Moves the amount from the available balance into a pending withdrawal request. An "
        "Orleeno admin pays it out (bank transfer is manual in this phase) or rejects it, which "
        "returns the amount to the balance."
    ),
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


@router.get(
    "/withdrawals",
    summary="My Withdrawal Requests",
    description="Pending, paid and rejected withdrawal requests.",
)
def list_withdrawals(
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return ProviderWalletService.list_withdrawals(db, current_provider["provider_id"])


@router.get(
    "/payout-details",
    summary="My Payout Details",
    description="Where withdrawals are sent. `ready` is false until a UPI ID or a full bank account is saved.",
)
def get_payout_details(db: Session = Depends(get_db), current_provider=Depends(get_current_provider)):
    return PayoutDetailsService.get_own(db, "provider", current_provider["provider_id"])


@router.put(
    "/payout-details",
    summary="Save Payout Details",
    description=(
        "Bank account (holder name, number, IFSC) and / or UPI ID. Required before the first "
        "withdrawal. The account number is stored encrypted."
    ),
)
def save_payout_details(
    payload: PayoutDetailsRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider)
):
    return PayoutDetailsService.save(db, "provider", current_provider["provider_id"], payload)
