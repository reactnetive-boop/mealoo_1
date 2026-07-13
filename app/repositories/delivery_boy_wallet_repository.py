from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.delivery_boy_wallet_model import DeliveryBoyWallet
from app.models.delivery_boy_wallet_transaction_model import DeliveryBoyWalletTransaction


class DeliveryBoyWalletRepository:

    @staticmethod
    def get_by_delivery_boy_id(db: Session, delivery_boy_id):
        return (
            db.query(DeliveryBoyWallet)
            .filter(DeliveryBoyWallet.delivery_boy_reference_id == delivery_boy_id)
            .first()
        )

    @staticmethod
    def get_or_create(db: Session, delivery_boy_id) -> DeliveryBoyWallet:
        wallet = (
            db.query(DeliveryBoyWallet)
            .filter(DeliveryBoyWallet.delivery_boy_reference_id == delivery_boy_id)
            .first()
        )
        if not wallet:
            wallet = DeliveryBoyWallet(
                delivery_boy_reference_id=delivery_boy_id,
                balance=Decimal("0.00"),
                total_earned=Decimal("0.00"),
                total_withdrawn=Decimal("0.00"),
            )
            db.add(wallet)
            db.flush()
        return wallet

    @staticmethod
    def credit(db: Session, wallet: DeliveryBoyWallet, amount: Decimal) -> DeliveryBoyWallet:
        wallet.balance += amount
        wallet.total_earned += amount
        db.flush()
        return wallet

    @staticmethod
    def debit(db: Session, wallet: DeliveryBoyWallet, amount: Decimal) -> DeliveryBoyWallet:
        wallet.balance -= amount
        wallet.total_withdrawn += amount
        db.flush()
        return wallet

    @staticmethod
    def create_transaction(db: Session, txn_data: dict) -> DeliveryBoyWalletTransaction:
        txn = DeliveryBoyWalletTransaction(**txn_data)
        db.add(txn)
        db.flush()
        return txn

    @staticmethod
    def get_transactions(
        db: Session,
        delivery_boy_id,
        txn_type: str = None,
        limit: int = 50
    ):
        query = (
            db.query(DeliveryBoyWalletTransaction)
            .filter(DeliveryBoyWalletTransaction.delivery_boy_reference_id == delivery_boy_id)
        )
        if txn_type:
            query = query.filter(DeliveryBoyWalletTransaction.type == txn_type)
        return (
            query
            .order_by(DeliveryBoyWalletTransaction.created_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_credits_since(db: Session, delivery_boy_id, since):
        """Payout credits on/after `since` — used for earnings summaries."""
        return (
            db.query(DeliveryBoyWalletTransaction)
            .filter(
                DeliveryBoyWalletTransaction.delivery_boy_reference_id == delivery_boy_id,
                DeliveryBoyWalletTransaction.type == "credit",
                DeliveryBoyWalletTransaction.created_at >= since
            )
            .all()
        )
