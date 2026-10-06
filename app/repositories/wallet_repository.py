from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction


class WalletRepository:

    @staticmethod
    def get_by_user_id(
        db: Session,
        user_id
    ):

        return (
            db.query(Wallet)
            .filter(
                Wallet.user_reference_id == user_id
            )
            .first()
        )

    @staticmethod
    def get_or_create(
        db: Session,
        user_id
    ):

        wallet = (
            db.query(Wallet)
            .filter(
                Wallet.user_reference_id == user_id
            )
            .first()
        )

        if not wallet:

            wallet = Wallet(
                user_reference_id=user_id,
                balance=Decimal("0.00")
            )

            db.add(wallet)

            db.flush()

        return wallet

    @staticmethod
    def create_transaction(
        db: Session,
        txn_data: dict
    ):

        txn = WalletTransaction(**txn_data)

        db.add(txn)

        db.flush()

        return txn

    @staticmethod
    def get_transactions_by_user(
        db: Session,
        user_id,
        limit: int = 50
    ):

        return (
            db.query(WalletTransaction)
            .filter(
                WalletTransaction.user_reference_id == user_id
            )
            .order_by(
                WalletTransaction.created_at.desc()
            )
            .limit(limit)
            .all()
        )
