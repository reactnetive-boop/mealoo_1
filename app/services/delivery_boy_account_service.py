from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.repositories.delivery_boy_repository import DeliveryBoyRepository as Repo
from app.repositories.delivery_boy_wallet_repository import DeliveryBoyWalletRepository
from app.schemas.delivery_boy_schema import DOCUMENT_TYPES
from app.utils.file_helper import save_delivery_document


class DeliveryBoyAccountService:

    # ── Documents ─────────────────────────────────────────

    @staticmethod
    def list_documents(db: Session, delivery_boy_id: str):
        documents = Repo.list_documents(db, delivery_boy_id)
        return {"success": True, "total": len(documents), "documents": documents}

    @staticmethod
    def upload_document(db: Session, delivery_boy_id: str, document_type: str, file: UploadFile):
        if document_type not in DOCUMENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid document_type. Allowed: {', '.join(DOCUMENT_TYPES)}"
            )

        file_url = save_delivery_document(file)
        document = Repo.upsert_document(db, delivery_boy_id, document_type, file_url)

        return {
            "success": True,
            "message": "Document uploaded",
            "document": document
        }

    # ── Payout details ────────────────────────────────────

    @staticmethod
    def get_payout_details(db: Session, delivery_boy_id: str):
        payout = Repo.get_payout_details(db, delivery_boy_id)
        return {"success": True, "payout_details": payout}

    @staticmethod
    def update_payout_details(db: Session, delivery_boy_id: str, payload):
        data = {k: v for k, v in payload.model_dump().items() if v is not None}
        if not data:
            raise HTTPException(status_code=400, detail="Nothing to update")

        payout = Repo.upsert_payout_details(db, delivery_boy_id, data)
        return {
            "success": True,
            "message": "Payout details saved",
            "payout_details": payout
        }

    # ── Wallet & earnings ─────────────────────────────────

    @staticmethod
    def get_wallet(db: Session, delivery_boy_id: str):
        wallet = DeliveryBoyWalletRepository.get_or_create(db, delivery_boy_id)
        db.commit()
        return {"success": True, "wallet": wallet}

    @staticmethod
    def get_transactions(db: Session, delivery_boy_id: str, txn_type: str = None, limit: int = 50):
        transactions = DeliveryBoyWalletRepository.get_transactions(
            db, delivery_boy_id, txn_type=txn_type, limit=limit
        )
        return {"success": True, "total": len(transactions), "transactions": transactions}

    @staticmethod
    def get_earnings_summary(db: Session, delivery_boy_id: str):
        wallet = DeliveryBoyWalletRepository.get_or_create(db, delivery_boy_id)
        db.commit()

        today = date.today()
        today_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
        week_start = today_start - timedelta(days=6)
        month_start = datetime.combine(today.replace(day=1), time.min, tzinfo=timezone.utc)

        credits = DeliveryBoyWalletRepository.get_credits_since(
            db, delivery_boy_id, min(week_start, month_start)
        )

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

    # ── Notifications ─────────────────────────────────────

    @staticmethod
    def list_notifications(db: Session, delivery_boy_id: str, limit: int = 50):
        notifications = Repo.list_notifications(db, delivery_boy_id, limit=limit)
        unread = Repo.count_unread_notifications(db, delivery_boy_id)
        return {
            "success": True,
            "total": len(notifications),
            "unread": unread,
            "notifications": notifications
        }

    @staticmethod
    def mark_notification_read(db: Session, delivery_boy_id: str, notification_id: str):
        notification = Repo.get_notification_by_id(db, delivery_boy_id, notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        Repo.mark_notification_read(db, notification)
        return {"success": True, "message": "Notification marked as read"}

    @staticmethod
    def mark_all_notifications_read(db: Session, delivery_boy_id: str):
        updated = Repo.mark_all_notifications_read(db, delivery_boy_id)
        return {"success": True, "message": f"{updated} notifications marked as read"}
