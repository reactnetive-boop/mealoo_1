from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import limit_by_ip
from app.dependencies.auth_dependency import get_delivery_session, get_active_delivery_boy
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
    DeliveryWithdrawalRequest,
)

router = APIRouter()


# ── State ─────────────────────────────────────────────────

@router.get(
    "/me/state",
    summary="Delivery Partner Account State",
    description=(
        "Single source of truth for app navigation. `next_step` is one of `account_inactive`, "
        "`personal_info`, `documents`, `vehicle`, `payout`, `application_rejected`, "
        "`awaiting_approval`, `dashboard`."
    ),
)
def get_state(db: Session = Depends(get_db), current=Depends(get_delivery_session)):
    return DeliveryBoyAccountService.get_state(db, current["delivery_boy_id"])


# ── Documents ─────────────────────────────────────────────

@router.get(
    "/documents",
    response_model=DeliveryBoyDocumentListResponse,
    summary="List My Documents",
    description="KYC documents with review `status` (`pending`, `verified`, `rejected`) and reviewer `remarks`.",
)
def list_documents(db: Session = Depends(get_db), current=Depends(get_active_delivery_boy)):
    return DeliveryBoyAccountService.list_documents(db, current["delivery_boy_id"])


@router.post(
    "/documents",
    response_model=DeliveryBoyDocumentUploadResponse,
    summary="Upload a Document",
    description=(
        "`multipart/form-data` with `document_type` (`aadhaar` | `pan` | `driving_license` | `vehicle_rc`) "
        "and `file` (JPEG / PNG / WEBP / PDF, max 5 MB). Re-uploading replaces the file and resets the "
        "review to `pending`. Files are private: only the owner and Orleeno admins can view them."
    ),
    dependencies=[Depends(limit_by_ip("delivery_doc_upload", 30, 3600))],
)
def upload_document(
    document_type: str = Form(..., description="aadhaar | pan | driving_license | vehicle_rc"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current=Depends(get_active_delivery_boy)
):
    return DeliveryBoyAccountService.upload_document(db, current["delivery_boy_id"], document_type, file)


@router.get("/documents/{document_id}/file", summary="View My Document File")
def get_document_file(document_id: UUID, db: Session = Depends(get_db), current=Depends(get_active_delivery_boy)):
    return DeliveryBoyAccountService.document_file(db, current["delivery_boy_id"], document_id)


# ── Payout details ────────────────────────────────────────

@router.get("/payout-details", response_model=GetPayoutDetailsResponse, summary="Get My Payout Details")
def get_payout_details(db: Session = Depends(get_db), current=Depends(get_active_delivery_boy)):
    return DeliveryBoyAccountService.get_payout_details(db, current["delivery_boy_id"])


@router.put(
    "/payout-details",
    response_model=UpdatePayoutDetailsResponse,
    summary="Save My Payout Details",
    description="Partial update: a UPI ID, bank account details, or both.",
)
def update_payout_details(
    payload: UpdatePayoutDetailsRequest,
    db: Session = Depends(get_db),
    current=Depends(get_active_delivery_boy)
):
    return DeliveryBoyAccountService.update_payout_details(db, current["delivery_boy_id"], payload)


# ── Wallet & earnings ─────────────────────────────────────

@router.get(
    "/wallet",
    response_model=GetWalletResponse,
    summary="Get My Wallet",
    description="Credited with the configured delivery payout for every completed delivery.",
)
def get_wallet(db: Session = Depends(get_db), current=Depends(get_active_delivery_boy)):
    return DeliveryBoyAccountService.get_wallet(db, current["delivery_boy_id"])


@router.get("/wallet/transactions", response_model=WalletTransactionListResponse, summary="List My Wallet Transactions")
def list_wallet_transactions(
    type: Optional[str] = Query(None, description="credit | debit"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current=Depends(get_active_delivery_boy)
):
    return DeliveryBoyAccountService.get_transactions(db, current["delivery_boy_id"], txn_type=type, limit=limit)


@router.post(
    "/wallet/withdraw",
    summary="Request a Withdrawal",
    description=(
        "Moves the amount from the balance into a pending withdrawal request. An Orleeno admin pays it "
        "to the saved payout details (manual transfer in this phase) or rejects it, which returns the amount."
    ),
    dependencies=[Depends(limit_by_ip("delivery_withdraw", 10, 3600))],
)
def request_withdrawal(
    payload: DeliveryWithdrawalRequest,
    db: Session = Depends(get_db),
    current=Depends(get_active_delivery_boy)
):
    return DeliveryBoyAccountService.request_withdrawal(db, current["delivery_boy_id"], payload)


@router.get("/wallet/withdrawals", summary="My Withdrawal Requests")
def list_withdrawals(db: Session = Depends(get_db), current=Depends(get_active_delivery_boy)):
    return DeliveryBoyAccountService.list_withdrawals(db, current["delivery_boy_id"])


@router.get(
    "/earnings",
    response_model=EarningsSummaryResponse,
    summary="Get My Earnings Summary",
    description="Delivery payouts today, in the last 7 days and this calendar month (business time zone).",
)
def get_earnings(db: Session = Depends(get_db), current=Depends(get_active_delivery_boy)):
    return DeliveryBoyAccountService.get_earnings_summary(db, current["delivery_boy_id"])


# ── Notifications ─────────────────────────────────────────

@router.get("/notifications", response_model=NotificationListResponse, summary="List My Notifications")
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current=Depends(get_delivery_session)
):
    return DeliveryBoyAccountService.list_notifications(db, current["delivery_boy_id"], limit=limit)


@router.put("/notifications/read-all", summary="Mark All Notifications Read")
def mark_all_notifications_read(db: Session = Depends(get_db), current=Depends(get_delivery_session)):
    return DeliveryBoyAccountService.mark_all_notifications_read(db, current["delivery_boy_id"])


@router.put("/notifications/{notification_id}/read", summary="Mark a Notification Read")
def mark_notification_read(notification_id: UUID, db: Session = Depends(get_db), current=Depends(get_delivery_session)):
    return DeliveryBoyAccountService.mark_notification_read(db, current["delivery_boy_id"], notification_id)
