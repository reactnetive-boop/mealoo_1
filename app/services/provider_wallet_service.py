from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.provider_wallet_repository import ProviderWalletRepository


class ProviderWalletService:

    @staticmethod
    def get_wallet_details(db: Session, provider_id: str):
        wallet = ProviderWalletRepository.get_or_create(db, provider_id)
        db.commit()

        transactions = ProviderWalletRepository.get_transactions(
            db, provider_id, limit=20
        )

        return {
            "success": True,
            "wallet": wallet,
            "recent_transactions": transactions
        }

    @staticmethod
    def get_transaction_history(
        db: Session,
        provider_id: str,
        txn_type: Optional[str] = None
    ):
        if txn_type and txn_type not in ("credit", "debit"):
            raise HTTPException(
                status_code=400,
                detail="type must be 'credit' or 'debit'"
            )

        transactions = ProviderWalletRepository.get_transactions(
            db, provider_id, txn_type=txn_type, limit=200
        )

        return {
            "success": True,
            "total": len(transactions),
            "transactions": transactions
        }

    @staticmethod
    def withdraw(db: Session, provider_id: str, payload):
        amount = Decimal(str(payload.amount))

        try:
            wallet = ProviderWalletRepository.get_or_create(db, provider_id)

            balance_before = Decimal(str(wallet.balance))

            if amount > balance_before:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient balance. Available: ₹{balance_before}"
                )

            ProviderWalletRepository.debit(db, wallet, amount)

            balance_after = Decimal(str(wallet.balance))

            ProviderWalletRepository.create_transaction(db, {
                "wallet_reference_id": wallet.provider_wallet_id,
                "provider_reference_id": provider_id,
                "type": "debit",
                "reason": "withdrawal",
                "amount": amount,
                "balance_before": balance_before,
                "balance_after": balance_after,
                "reference_type": "withdrawal",
                "description": payload.description,
            })

            db.commit()

            return {
                "success": True,
                "message": "Withdrawal processed successfully",
                "balance_before": balance_before,
                "amount_withdrawn": amount,
                "balance_after": balance_after
            }

        except HTTPException:
            raise

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Withdrawal failed: {str(e)}")

    @staticmethod
    def credit_for_order(
        db: Session,
        provider_id: str,
        amount: Decimal,
        reference_id,
        reference_type: str,
        description: str = None
    ):
        """
        Called internally when a subscription order or extra order
        is marked as delivered. Adds earnings to the provider wallet.
        """
        wallet = ProviderWalletRepository.get_or_create(db, provider_id)

        balance_before = Decimal(str(wallet.balance))

        ProviderWalletRepository.credit(db, wallet, amount)

        balance_after = Decimal(str(wallet.balance))

        ProviderWalletRepository.create_transaction(db, {
            "wallet_reference_id": wallet.provider_wallet_id,
            "provider_reference_id": provider_id,
            "type": "credit",
            "reason": "order_delivered",
            "amount": amount,
            "balance_before": balance_before,
            "balance_after": balance_after,
            "reference_id": reference_id,
            "reference_type": reference_type,
            "description": description,
        })
