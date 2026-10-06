from datetime import timedelta
from decimal import Decimal

from fastapi import UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.clock import today_local, local_datetime
from app.domain import ledger
from app.models.delivery_boy_document_model import DeliveryBoyDocument
from app.repositories.delivery_boy_repository import DeliveryBoyRepository as Repo
from app.repositories.delivery_boy_wallet_repository import DeliveryBoyWalletRepository
from app.schemas.delivery_boy_schema import DOCUMENT_TYPES
from app.services.payout_service import PayoutService
from app.utils.file_helper import save_delivery_document, delete_upload, read_upload, content_type_of

from datetime import time
from app.core.errors import DomainError


def document_file_response(doc: DeliveryBoyDocument) -> Response:
    data = read_upload(doc.file_url)
    if data is None:
        raise DomainError("File not found", 404)
    return Response(
        content=data,
        media_type=content_type_of(doc.file_url),
        headers={"Cache-Control": "private, no-store", "Content-Disposition": "inline"},
    )


class DeliveryBoyAccountService:

    # ── State (drives app navigation) ─────────────────────

    @staticmethod
    def get_state(db: Session, delivery_boy_id: str) -> dict:
        boy = Repo.get_by_id(db, delivery_boy_id)
        docs = {d.document_type: d.status for d in Repo.list_documents(db, delivery_boy_id)}
        payout = Repo.get_payout_details(db, delivery_boy_id)

        profile_completed = bool(boy.full_name and boy.email and boy.date_of_birth and boy.gender)
        documents_uploaded = all(t in docs for t in DOCUMENT_TYPES)
        documents_verified = all(docs.get(t) == "verified" for t in DOCUMENT_TYPES)
        documents_rejected = [t for t in DOCUMENT_TYPES if docs.get(t) == "rejected"]
        vehicle_completed = bool(boy.vehicle_type and boy.vehicle_number)
        payout_completed = bool(payout and (payout.upi_id or (payout.account_number and payout.ifsc_code)))

        if not boy.is_active:
            next_step = "account_inactive"
        elif not profile_completed:
            next_step = "personal_info"
        elif not documents_uploaded or documents_rejected:
            next_step = "documents"
        elif not vehicle_completed:
            next_step = "vehicle"
        elif not payout_completed:
            next_step = "payout"
        elif boy.approval_status == "rejected":
            next_step = "application_rejected"
        elif boy.approval_status != "approved":
            next_step = "awaiting_approval"
        else:
            next_step = "dashboard"

        return {
            "success": True,
            "delivery_boy_id": str(boy.delivery_boy_id),
            "is_authenticated": True,
            "is_mobile_verified": bool(boy.is_mobile_verified),
            "is_active": bool(boy.is_active),
            "is_profile_completed": profile_completed,
            "documents_status": {t: docs.get(t, "missing") for t in DOCUMENT_TYPES},
            "documents_completed": documents_uploaded and not documents_rejected,
            "documents_verified": documents_verified,
            "vehicle_completed": vehicle_completed,
            "payout_completed": payout_completed,
            "approval_status": boy.approval_status,
            "approval_note": boy.approval_note,
            "is_online": bool(boy.is_online),
            "next_step": next_step,
        }

    # ── Documents ─────────────────────────────────────────

    @staticmethod
    def list_documents(db: Session, delivery_boy_id: str):
        documents = Repo.list_documents(db, delivery_boy_id)
        return {
            "success": True,
            "total": len(documents),
            "documents": [
                {
                    "delivery_boy_document_id": d.delivery_boy_document_id,
                    "document_type": d.document_type,
                    "file_url": None,
                    "status": d.status,
                    "remarks": d.remarks,
                    "created_at": d.created_at,
                    "updated_at": d.updated_at,
                }
                for d in documents
            ],
        }

    @staticmethod
    def upload_document(db: Session, delivery_boy_id: str, document_type: str, file: UploadFile):
        if document_type not in DOCUMENT_TYPES:
            raise DomainError(f"Invalid document_type. Allowed: {', '.join(DOCUMENT_TYPES)}", 400)
        existing = Repo.get_document_by_type(db, delivery_boy_id, document_type)
        if existing and existing.status == "verified":
            raise DomainError("This document is already verified", 400)

        old_path = existing.file_url if existing else None
        file_url = save_delivery_document(file)
        document = Repo.upsert_document(db, delivery_boy_id, document_type, file_url)
        document.remarks = None
        db.commit()
        if old_path and old_path != file_url:
            delete_upload(old_path)

        return {
            "success": True,
            "message": "Document uploaded",
            "document": {
                "delivery_boy_document_id": document.delivery_boy_document_id,
                "document_type": document.document_type,
                "file_url": None,
                "status": document.status,
                "remarks": None,
                "created_at": document.created_at,
                "updated_at": document.updated_at,
            },
        }

    @staticmethod
    def document_file(db: Session, delivery_boy_id: str, document_id):
        doc = db.query(DeliveryBoyDocument).filter(
            DeliveryBoyDocument.delivery_boy_document_id == document_id,
            DeliveryBoyDocument.delivery_boy_reference_id == delivery_boy_id,
        ).first()
        if doc is None:
            raise DomainError("Document not found", 404)
        return document_file_response(doc)

    # ── Payout details ────────────────────────────────────

    @staticmethod
    def get_payout_details(db: Session, delivery_boy_id: str):
        return {"success": True, "payout_details": Repo.get_payout_details(db, delivery_boy_id)}

    @staticmethod
    def update_payout_details(db: Session, delivery_boy_id: str, payload):
        data = {k: v for k, v in payload.model_dump().items() if v is not None}
        if not data:
            raise DomainError("Nothing to update", 400)
        if "ifsc_code" in data:
            data["ifsc_code"] = data["ifsc_code"].upper()
        payout = Repo.upsert_payout_details(db, delivery_boy_id, data)
        db.commit()
        return {"success": True, "message": "Payout details saved", "payout_details": payout}

    # ── Wallet & earnings ─────────────────────────────────

    @staticmethod
    def get_wallet(db: Session, delivery_boy_id: str):
        wallet = ledger.lock_delivery_wallet(db, delivery_boy_id)
        db.commit()
        return {"success": True, "wallet": wallet}

    @staticmethod
    def get_transactions(db: Session, delivery_boy_id: str, txn_type: str = None, limit: int = 50):
        if txn_type and txn_type not in ("credit", "debit"):
            raise DomainError("type must be 'credit' or 'debit'", 400)
        transactions = DeliveryBoyWalletRepository.get_transactions(db, delivery_boy_id, txn_type=txn_type, limit=limit)
        return {"success": True, "total": len(transactions), "transactions": transactions}

    @staticmethod
    def get_earnings_summary(db: Session, delivery_boy_id: str):
        wallet = ledger.lock_delivery_wallet(db, delivery_boy_id)
        db.commit()

        today = today_local()
        today_start = local_datetime(today, time.min)
        week_start = today_start - timedelta(days=6)
        month_start = local_datetime(today.replace(day=1), time.min)

        credits = [
            c for c in DeliveryBoyWalletRepository.get_credits_since(db, delivery_boy_id, min(week_start, month_start))
            if c.reason == "delivery_payout"
        ]

        def summarize(since):
            in_period = [c for c in credits if c.created_at and c.created_at >= since]
            return {
                "deliveries": len(in_period),
                "earnings": sum((c.amount for c in in_period), Decimal("0.00")),
            }

        return {
            "success": True,
            "wallet": wallet,
            "today": summarize(today_start),
            "week": summarize(week_start),
            "month": summarize(month_start),
        }

    @staticmethod
    def request_withdrawal(db: Session, delivery_boy_id: str, payload):
        return PayoutService.request(db, "delivery_boy", delivery_boy_id, payload.amount, payload.note)

    @staticmethod
    def list_withdrawals(db: Session, delivery_boy_id: str):
        return PayoutService.list_for_owner(db, "delivery_boy", delivery_boy_id)

    # ── Notifications ─────────────────────────────────────

    @staticmethod
    def list_notifications(db: Session, delivery_boy_id: str, limit: int = 50):
        notifications = Repo.list_notifications(db, delivery_boy_id, limit=limit)
        unread = Repo.count_unread_notifications(db, delivery_boy_id)
        return {"success": True, "total": len(notifications), "unread": unread, "notifications": notifications}

    @staticmethod
    def mark_notification_read(db: Session, delivery_boy_id: str, notification_id):
        notification = Repo.get_notification_by_id(db, delivery_boy_id, notification_id)
        if not notification:
            raise DomainError("Notification not found", 404)
        Repo.mark_notification_read(db, notification)
        db.commit()
        return {"success": True, "message": "Notification marked as read"}

    @staticmethod
    def mark_all_notifications_read(db: Session, delivery_boy_id: str):
        updated = Repo.mark_all_notifications_read(db, delivery_boy_id)
        db.commit()
        return {"success": True, "message": f"{updated} notifications marked as read"}
