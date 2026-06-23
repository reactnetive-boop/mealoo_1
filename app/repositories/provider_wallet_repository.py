from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.provider_wallet_model import ProviderWallet
from app.models.provider_wallet_transaction_model import ProviderWalletTransaction


class ProviderWalletRepository:

    @staticmethod
    def get_by_provider_id(db: Session, provider_id):
        return (
            db.query(ProviderWallet)
            .filter(ProviderWallet.provider_reference_id == provider_id)
            .first()
        )

    @staticmethod
    def get_or_create(db: Session, provider_id) -> ProviderWallet:
        wallet = (
            db.query(ProviderWallet)
            .filter(ProviderWallet.provider_reference_id == provider_id)
            .first()
        )
        if not wallet:
            wallet = ProviderWallet(
                provider_reference_id=provider_id,
                balance=Decimal("0.00"),
                total_earned=Decimal("0.00"),
                total_withdrawn=Decimal("0.00"),
            )
            db.add(wallet)
            db.flush()
        return wallet

    @staticmethod
    def credit(db: Session, wallet: ProviderWallet, amount: Decimal) -> ProviderWallet:
        wallet.balance += amount
        wallet.total_earned += amount
        db.flush()
        return wallet

    @staticmethod
    def debit(db: Session, wallet: ProviderWallet, amount: Decimal) -> ProviderWallet:
        wallet.balance -= amount
        wallet.total_withdrawn += amount
        db.flush()
        return wallet

    @staticmethod
    def create_transaction(db: Session, txn_data: dict) -> ProviderWalletTransaction:
        txn = ProviderWalletTransaction(**txn_data)
        db.add(txn)
        db.flush()
        return txn

    @staticmethod
    def get_transactions(
        db: Session,
        provider_id,
        txn_type: str = None,
        limit: int = 50
    ):
        query = (
            db.query(ProviderWalletTransaction)
            .filter(ProviderWalletTransaction.provider_reference_id == provider_id)
        )
        if txn_type:
            query = query.filter(ProviderWalletTransaction.type == txn_type)
        return (
            query
            .order_by(ProviderWalletTransaction.created_at.desc())
            .limit(limit)
            .all()
        )
