from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_delivery_boy
from app.services.delivery_boy_account_service import DeliveryBoyAccountService
from app.schemas.delivery_boy_schema import (
    DeliveryBoyDocumentListResponse,
    DeliveryBoyDocumentUploadResponse,
    GetPayoutDetailsResponse,
    UpdatePayoutDetailsRequest,
    UpdatePayoutDetailsResponse,
    GetWalletResponse,
    WalletTransactionListResponse,
    EarningsSummaryResponse,
    NotificationListResponse,
)

router = APIRouter()


# ── Documents ─────────────────────────────────────────────

@router.get(
    "/documents",
    response_model=DeliveryBoyDocumentListResponse,
    summary="List My Documents",
    description=(
        "**Fetch all KYC documents uploaded by this delivery boy.**\n\n"
        "Each document has a `status`: `pending` (awaiting review), `verified`, or `rejected`.\n\n"
        "**When to call:** On the Upload Documents screen to show what's already uploaded."
    )
)
def list_documents(
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyAccountService.list_documents(db, current["delivery_boy_id"])


@router.post(
    "/documents",
    response_model=DeliveryBoyDocumentUploadResponse,
    summary="Upload a Document",
    description=(
        "**Upload or replace a KYC document.**\n\n"
        "Send `multipart/form-data` with a `document_type` field "
        "(`aadhaar` | `pan` | `driving_license` | `vehicle_rc`) and the image as `file`. "
        "Re-uploading the same type replaces the previous file and resets status to `pending`.\n\n"
        "**When to call:** From the Upload Documents onboarding step."
    )
)
async def upload_document(
    document_type: str = Form(..., description="aadhaar | pan | driving_license | vehicle_rc"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyAccountService.upload_document(
        db, current["delivery_boy_id"], document_type, file
    )


# ── Payout details ────────────────────────────────────────

@router.get(
    "/payout-details",
    response_model=GetPayoutDetailsResponse,
    summary="Get My Payout Details",
    description=(
        "**Fetch saved bank account / UPI payout details.**\n\n"
        "`payout_details` is `null` until the delivery boy saves them once.\n\n"
        "**When to call:** To pre-fill the Bank & UPI screen."
    )
)
def get_payout_details(
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyAccountService.get_payout_details(db, current["delivery_boy_id"])


@router.put(
    "/payout-details",
    response_model=UpdatePayoutDetailsResponse,
    summary="Save My Payout Details",
    description=(
        "**Create or update bank account / UPI details for payouts.**\n\n"
        "Partial update: only the fields you send are changed. "
        "A delivery boy can save just a UPI ID, just bank details, or both.\n\n"
        "**When to call:** From the Bank & UPI onboarding step or profile settings."
    )
)
def update_payout_details(
    payload: UpdatePayoutDetailsRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyAccountService.update_payout_details(
        db, current["delivery_boy_id"], payload
    )


# ── Wallet & earnings ─────────────────────────────────────

@router.get(
    "/wallet",
    response_model=GetWalletResponse,
    summary="Get My Wallet",
    description=(
        "**Fetch the delivery boy's wallet balance and lifetime totals.**\n\n"
        "The wallet is credited automatically on every completed delivery.\n\n"
        "**When to call:** On the Wallet screen."
    )
)
def get_wallet(
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyAccountService.get_wallet(db, current["delivery_boy_id"])


@router.get(
    "/wallet/transactions",
    response_model=WalletTransactionListResponse,
    summary="List My Wallet Transactions",
    description=(
        "**Fetch wallet transaction history, newest first.**\n\n"
        "Filter by `type` (`credit` | `debit`). Each credit references the delivered "
        "order via `reference_id`/`reference_type`.\n\n"
        "**When to call:** On the Transaction History screen."
    )
)
def list_wallet_transactions(
    type: Optional[str] = Query(None, description="credit | debit"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyAccountService.get_transactions(
        db, current["delivery_boy_id"], txn_type=type, limit=limit
    )


@router.get(
    "/earnings",
    response_model=EarningsSummaryResponse,
    summary="Get My Earnings Summary",
    description=(
        "**Earnings dashboard numbers: today, last 7 days, and this calendar month.**\n\n"
        "`deliveries` counts payout credits in the period; `earnings` sums them. "
        "Also returns the current wallet snapshot.\n\n"
        "**When to call:** On the Earnings screen."
    )
)
def get_earnings(
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyAccountService.get_earnings_summary(db, current["delivery_boy_id"])


# ── Notifications ─────────────────────────────────────────

@router.get(
    "/notifications",
    response_model=NotificationListResponse,
    summary="List My Notifications",
    description=(
        "**Fetch notifications for this delivery boy, newest first.**\n\n"
        "Created automatically when an order is assigned and when a payout is credited.\n\n"
        "**When to call:** On the Notifications screen; poll or refresh on app focus."
    )
)
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyAccountService.list_notifications(
        db, current["delivery_boy_id"], limit=limit
    )


@router.put(
    "/notifications/read-all",
    summary="Mark All Notifications Read",
    description="**Mark every unread notification as read.**"
)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyAccountService.mark_all_notifications_read(
        db, current["delivery_boy_id"]
    )


@router.put(
    "/notifications/{notification_id}/read",
    summary="Mark a Notification Read",
    description="**Mark a single notification as read.**"
)
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current=Depends(get_current_delivery_boy)
):
    return DeliveryBoyAccountService.mark_notification_read(
        db, current["delivery_boy_id"], notification_id
    )
