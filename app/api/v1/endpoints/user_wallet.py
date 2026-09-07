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
    response_model=WalletDetailsResponse,
    summary="Get Wallet Balance",
    description=(
        "**Fetch the user's current wallet balance.**\n\n"
        "Always check the wallet balance before allowing the user to subscribe or place an extra order. "
        "If the balance is less than the order total, prompt the user to recharge first.\n\n"
        "**When to call:** On the wallet screen, and before the subscription / order checkout flow."
    )
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
    response_model=WalletTransactionListResponse,
    summary="Wallet Transaction History",
    description=(
        "**Fetch all credit and debit transactions for the user's wallet.**\n\n"
        "Each entry includes transaction type (`credit`/`debit`), amount, description, "
        "and timestamp. Use this to render the transaction history on the wallet screen.\n\n"
        "**When to call:** When the user opens 'Transaction History' from the wallet screen."
    )
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
    response_model=WalletRechargeResponse,
    summary="Recharge Wallet",
    description=(
        "**Add money to the user's wallet.**\n\n"
        "Send `amount` (in INR). In a real implementation this would be called after a payment "
        "gateway confirms a successful transaction. Returns the updated balance.\n\n"
        "**When to call:** After the user completes payment on the recharge screen, "
        "or when the checkout flow detects insufficient balance.\n\n"
        "**Flow:** Check balance (`GET /user/wallet`) → insufficient → payment gateway → "
        "`POST /user/wallet/recharge` → retry subscription / order"
    )
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
