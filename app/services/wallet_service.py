from decimal import Decimal

from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.repositories.wallet_repository import WalletRepository


class WalletService:

    @staticmethod
    def get_wallet_details(
        db: Session,
        user_id: str
    ):

        wallet = WalletRepository.get_by_user_id(
            db,
            user_id
        )

        if not wallet:

            raise HTTPException(
                status_code=404,
                detail="Wallet not found. Please recharge to create your wallet."
            )

        transactions = (
            WalletRepository.get_transactions_by_user(
                db,
                user_id
            )
        )

        return {
            "success": True,
            "wallet": wallet,
            "transactions": transactions
        }

    @staticmethod
    def get_transaction_history(
        db: Session,
        user_id: str
    ):

        transactions = (
            WalletRepository.get_transactions_by_user(
                db,
                user_id
            )
        )

        return {
            "success": True,
            "total": len(transactions),
            "transactions": transactions
        }

    @staticmethod
    def recharge(
        db: Session,
        user_id: str,
        payload
    ):

        amount = Decimal(str(payload.amount))

        try:

            wallet = WalletRepository.get_or_create(
                db,
                user_id
            )

            balance_before = Decimal(str(wallet.balance))

            WalletRepository.credit_balance(
                db,
                wallet,
                amount
            )

            balance_after = Decimal(str(wallet.balance))

            txn_data = {
                "wallet_reference_id": wallet.wallet_id,
                "user_reference_id": user_id,
                "type": "credit",
                "reason": "topup",
                "amount": amount,
                "balance_before": balance_before,
                "balance_after": balance_after,
                "description": payload.description,
                "created_by": user_id
            }

            WalletRepository.create_transaction(
                db,
                txn_data
            )

            db.commit()

            return {
                "success": True,
                "message": "Wallet recharged successfully",
                "balance_before": balance_before,
                "amount_added": amount,
                "balance_after": balance_after
            }

        except Exception as e:

            db.rollback()

            raise HTTPException(
                status_code=500,
                detail=f"Recharge failed: {str(e)}"
            )
