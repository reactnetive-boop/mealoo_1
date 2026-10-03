"""
Wallet ledgers (customer, kitchen, delivery partner) and the platform ledger.

Rules enforced here for every money movement:
  * the wallet row is locked (SELECT ... FOR UPDATE) before its balance is
    read, so concurrent requests serialise instead of overspending;
  * every movement writes a transaction row with balance before / after;
  * every movement carries an idempotency key; posting the same key twice is
    a no-op, so retries and replays cannot pay or refund twice;
  * amounts must be positive and a debit can never take a balance below 0.

Callers own the transaction: nothing here commits.
"""

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.clock import now_utc
from app.domain.pricing import money, ZERO
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction
from app.models.provider_wallet_model import ProviderWallet
from app.models.provider_wallet_transaction_model import ProviderWalletTransaction
from app.models.delivery_boy_wallet_model import DeliveryBoyWallet
from app.models.delivery_boy_wallet_transaction_model import DeliveryBoyWalletTransaction
from app.models.platform_ledger_model import PlatformLedgerEntry


class InsufficientBalance(DomainError):

    def __init__(self, required: Decimal, available: Decimal):
        super().__init__(
            f"Insufficient wallet balance. Required: {money(required)}, Available: {money(available)}",
            400,
            code="INSUFFICIENT_BALANCE",
        )
        self.required = required
        self.available = available


def _positive(amount) -> Decimal:
    amount = money(amount)
    if amount <= ZERO:
        raise DomainError("Amount must be greater than 0")
    return amount


# ── Customer wallet ───────────────────────────────────────────

def lock_customer_wallet(db: Session, user_id) -> Wallet:
    db.execute(
        text(
            "INSERT INTO subscription.wallets (wallet_id, user_reference_id, balance) "
            "VALUES (gen_random_uuid(), :uid, 0) ON CONFLICT (user_reference_id) DO NOTHING"
        ),
        {"uid": str(user_id)},
    )
    return (
        db.query(Wallet)
        .filter(Wallet.user_reference_id == user_id)
        .populate_existing()
        .with_for_update()
        .one()
    )


def customer_txn_exists(db: Session, idempotency_key: str) -> WalletTransaction | None:
    return (
        db.query(WalletTransaction)
        .filter(WalletTransaction.idempotency_key == idempotency_key)
        .first()
    )


def post_customer(
    db: Session,
    user_id,
    *,
    type: str,
    amount,
    reason: str,
    idempotency_key: str,
    reference_type: str | None = None,
    reference_id=None,
    description: str | None = None,
    created_by=None,
    wallet: Wallet | None = None,
) -> WalletTransaction:
    """Credit or debit a customer wallet once per idempotency key."""

    amount = _positive(amount)
    wallet = wallet or lock_customer_wallet(db, user_id)

    existing = customer_txn_exists(db, idempotency_key)
    if existing:
        return existing

    before = money(wallet.balance)
    if type == "debit":
        if before < amount:
            raise InsufficientBalance(amount, before)
        after = before - amount
    elif type == "credit":
        after = before + amount
    else:
        raise ValueError("type must be credit or debit")

    wallet.balance = after
    txn = WalletTransaction(
        wallet_reference_id=wallet.wallet_id,
        user_reference_id=user_id,
        type=type,
        reason=reason,
        amount=amount,
        balance_before=before,
        balance_after=after,
        reference_id=reference_id,
        reference_type=reference_type,
        description=description,
        created_by=created_by,
        idempotency_key=idempotency_key,
        created_at=now_utc(),
    )
    db.add(txn)
    db.flush()
    return txn


# ── Kitchen wallet ────────────────────────────────────────────

def lock_provider_wallet(db: Session, provider_id) -> ProviderWallet:
    db.execute(
        text(
            "INSERT INTO provider.provider_wallets "
            "(provider_wallet_id, provider_reference_id, balance, total_earned, total_withdrawn) "
            "VALUES (gen_random_uuid(), :pid, 0, 0, 0) ON CONFLICT (provider_reference_id) DO NOTHING"
        ),
        {"pid": str(provider_id)},
    )
    return (
        db.query(ProviderWallet)
        .filter(ProviderWallet.provider_reference_id == provider_id)
        .populate_existing()
        .with_for_update()
        .one()
    )


def post_provider(
    db: Session,
    provider_id,
    *,
    type: str,
    amount,
    reason: str,
    idempotency_key: str,
    reference_type: str | None = None,
    reference_id=None,
    description: str | None = None,
    counts_as_earning: bool = False,
    counts_as_withdrawal: bool = False,
) -> ProviderWalletTransaction:

    amount = _positive(amount)
    wallet = lock_provider_wallet(db, provider_id)

    existing = (
        db.query(ProviderWalletTransaction)
        .filter(ProviderWalletTransaction.idempotency_key == idempotency_key)
        .first()
    )
    if existing:
        return existing

    before = money(wallet.balance)
    if type == "debit":
        if before < amount:
            raise InsufficientBalance(amount, before)
        after = before - amount
    else:
        after = before + amount

    wallet.balance = after
    if counts_as_earning:
        wallet.total_earned = money(wallet.total_earned) + amount
    if counts_as_withdrawal:
        wallet.total_withdrawn = money(wallet.total_withdrawn) + amount

    txn = ProviderWalletTransaction(
        wallet_reference_id=wallet.provider_wallet_id,
        provider_reference_id=provider_id,
        type=type,
        reason=reason,
        amount=amount,
        balance_before=before,
        balance_after=after,
        reference_id=reference_id,
        reference_type=reference_type,
        description=description,
        idempotency_key=idempotency_key,
        created_at=now_utc(),
    )
    db.add(txn)
    db.flush()
    return txn


# ── Delivery partner wallet ───────────────────────────────────

def lock_delivery_wallet(db: Session, delivery_boy_id) -> DeliveryBoyWallet:
    db.execute(
        text(
            "INSERT INTO delivery.delivery_boy_wallets "
            "(delivery_boy_wallet_id, delivery_boy_reference_id, balance, total_earned, total_withdrawn) "
            "VALUES (gen_random_uuid(), :did, 0, 0, 0) ON CONFLICT (delivery_boy_reference_id) DO NOTHING"
        ),
        {"did": str(delivery_boy_id)},
    )
    return (
        db.query(DeliveryBoyWallet)
        .filter(DeliveryBoyWallet.delivery_boy_reference_id == delivery_boy_id)
        .populate_existing()
        .with_for_update()
        .one()
    )


def post_delivery(
    db: Session,
    delivery_boy_id,
    *,
    type: str,
    amount,
    reason: str,
    idempotency_key: str,
    reference_type: str | None = None,
    reference_id=None,
    description: str | None = None,
    counts_as_earning: bool = False,
    counts_as_withdrawal: bool = False,
) -> DeliveryBoyWalletTransaction:

    amount = _positive(amount)
    wallet = lock_delivery_wallet(db, delivery_boy_id)

    existing = (
        db.query(DeliveryBoyWalletTransaction)
        .filter(DeliveryBoyWalletTransaction.idempotency_key == idempotency_key)
        .first()
    )
    if existing:
        return existing

    before = money(wallet.balance)
    if type == "debit":
        if before < amount:
            raise InsufficientBalance(amount, before)
        after = before - amount
    else:
        after = before + amount

    wallet.balance = after
    if counts_as_earning:
        wallet.total_earned = money(wallet.total_earned) + amount
    if counts_as_withdrawal:
        wallet.total_withdrawn = money(wallet.total_withdrawn) + amount

    txn = DeliveryBoyWalletTransaction(
        wallet_reference_id=wallet.delivery_boy_wallet_id,
        delivery_boy_reference_id=delivery_boy_id,
        type=type,
        reason=reason,
        amount=amount,
        balance_before=before,
        balance_after=after,
        reference_id=reference_id,
        reference_type=reference_type,
        description=description,
        idempotency_key=idempotency_key,
        created_at=now_utc(),
    )
    db.add(txn)
    db.flush()
    return txn


# ── Platform ledger ───────────────────────────────────────────

def post_platform(
    db: Session,
    *,
    entry_type: str,
    direction: str,
    amount,
    reference_type: str,
    reference_id,
    idempotency_key: str,
    description: str | None = None,
) -> PlatformLedgerEntry | None:
    amount = money(amount)
    if amount <= ZERO:
        return None
    existing = (
        db.query(PlatformLedgerEntry)
        .filter(PlatformLedgerEntry.idempotency_key == idempotency_key)
        .first()
    )
    if existing:
        return existing
    entry = PlatformLedgerEntry(
        entry_type=entry_type,
        direction=direction,
        amount=amount,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
        idempotency_key=idempotency_key,
        created_at=now_utc(),
    )
    db.add(entry)
    db.flush()
    return entry
