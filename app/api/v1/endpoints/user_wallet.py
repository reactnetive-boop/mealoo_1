from fastapi import APIRouter, Depends, Header

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import limit_by_ip
from app.dependencies.auth_dependency import get_current_user
from app.schemas.wallet_schema import (
    WalletRechargeRequest,
    WalletRechargeResponse,
    WalletDetailsResponse,
    WalletTransactionListResponse
)
from app.services.wallet_service import WalletService
from app.schemas.payout_schema import (
    CustomerWithdrawalRequest,
    PayoutDetailsRequest,
    TopupOrderRequest,
    TopupVerifyRequest,
)
from app.services.razorpay_service import RazorpayService
from app.services.payout_details_service import PayoutDetailsService
from app.services.payout_service import PayoutService

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
    summary="Add Money (internal wallet top-up)",
    description=(
        "Internal wallet top-up for the current phase: no payment gateway is connected and no "
        "UPI / card transaction takes place. Each top-up is recorded as a payment with method "
        "`internal_wallet` and a ledger credit. Limited per top-up and per day; send an "
        "`Idempotency-Key` header so a retried request is not credited twice."
    ),
    dependencies=[Depends(limit_by_ip("wallet_topup", 20, 3600))],
)
def recharge_wallet(
    payload: WalletRechargeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=80),
):

    return WalletService.recharge(
        db,
        current_user["user_id"],
        payload,
        idempotency_key,
    )



# ── Withdrawing wallet money ──────────────────────────────────

@router.get(
    "/payout-details",
    summary="My Bank / UPI for Withdrawals",
    description="`ready` is false until a UPI ID or a full bank account is saved.",
)
def get_payout_details(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return PayoutDetailsService.get_own(db, "customer", current_user["user_id"])


@router.put(
    "/payout-details",
    summary="Save Bank / UPI for Withdrawals",
    description="The account number is stored encrypted.",
)
def save_payout_details(payload: PayoutDetailsRequest, db: Session = Depends(get_db),
                        current_user=Depends(get_current_user)):
    return PayoutDetailsService.save(db, "customer", current_user["user_id"], payload)


@router.post(
    "/withdraw",
    summary="Withdraw Wallet Balance",
    description=(
        "Moves the amount out of the wallet into a pending request; Orleeno transfers it to the saved "
        "bank / UPI and marks it paid, or rejects it and the money returns to the wallet."
    ),
    dependencies=[Depends(limit_by_ip("wallet_withdraw", 10, 3600))],
)
def withdraw(payload: CustomerWithdrawalRequest, db: Session = Depends(get_db),
             current_user=Depends(get_current_user)):
    return PayoutService.request(db, "customer", current_user["user_id"], payload.amount, payload.note)


@router.get("/withdrawals", summary="My Withdrawal Requests")
def withdrawals(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return PayoutService.list_for_owner(db, "customer", current_user["user_id"])



# ── Online top-up (Razorpay; off unless PAYMENT_GATEWAY=razorpay) ──

@router.post(
    "/topup/order",
    summary="Start an Online Top-Up",
    description="Creates a Razorpay order; open Razorpay Checkout with `razorpay_order_id` and `razorpay_key_id`.",
    dependencies=[Depends(limit_by_ip("wallet_gateway", 20, 3600))],
)
def topup_order(payload: TopupOrderRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return RazorpayService.create_order(db, current_user["user_id"], payload.amount)


@router.post(
    "/topup/verify",
    summary="Finish an Online Top-Up",
    description="Send what Razorpay Checkout returned. The wallet is credited once, even if the webhook also arrives.",
)
def topup_verify(payload: TopupVerifyRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return RazorpayService.verify(db, current_user["user_id"], payload)
