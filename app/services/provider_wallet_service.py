from typing import Optional

from sqlalchemy.orm import Session

from app.domain import ledger
from app.repositories.provider_wallet_repository import ProviderWalletRepository
from app.services.payout_service import PayoutService
from app.core.errors import DomainError


class ProviderWalletService:

    @staticmethod
    def get_wallet_details(db: Session, provider_id: str):
        wallet = ledger.lock_provider_wallet(db, provider_id)
        db.commit()
        transactions = ProviderWalletRepository.get_transactions(db, provider_id, limit=20)
        pending = PayoutService.list_for_owner(db, "provider", provider_id)["requests"]
        return {
            "success": True,
            "wallet": wallet,
            "pending_withdrawals": [r for r in pending if r["status"] == "pending"],
            "recent_transactions": transactions,
        }

    @staticmethod
    def get_transaction_history(db: Session, provider_id: str, txn_type: Optional[str] = None):
        if txn_type and txn_type not in ("credit", "debit"):
            raise DomainError("type must be 'credit' or 'debit'", 400)
        transactions = ProviderWalletRepository.get_transactions(db, provider_id, txn_type=txn_type, limit=200)
        return {"success": True, "total": len(transactions), "transactions": transactions}

    @staticmethod
    def withdraw(db: Session, provider_id: str, payload):
        result = PayoutService.request(db, "provider", provider_id, payload.amount, payload.description)
        wallet = ledger.lock_provider_wallet(db, provider_id)
        db.commit()
        request = result["request"]
        return {
            "success": True,
            "message": result["message"],
            "balance_before": wallet.balance + request["amount"],
            "amount_withdrawn": request["amount"],
            "balance_after": wallet.balance,
            "request": request,
        }

    @staticmethod
    def list_withdrawals(db: Session, provider_id: str):
        return PayoutService.list_for_owner(db, "provider", provider_id)
