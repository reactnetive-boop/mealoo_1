"""
Wallet ledgers (customer, kitchen, delivery partner) and the platform ledger.

Rules enforced here for every money movement:
  * the wallet row is locked (SELECT ... FOR UPDATE) before its balance is
    read, so concurrent requests serialise instead of overspending;
  * every movement writes a transaction row with balance before / after;
  * every movement carries an idempotency key; posting the same key twice is
    a no-op, so retries and replays cannot pay or refund twice. Reusing a key
    for a *different* movement (other type or amount) is refused;
  * amounts must be positive and a debit can never take a balance below 0.

The three wallet kinds share one poster (`_post`) driven by a `_WalletSpec`.
Callers own the transaction: nothing here commits.
"""

from dataclasses import dataclass, field
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


def _idempotency_conflict() -> DomainError:
    return DomainError(
        "Idempotency key reused for a different money movement", 409, code="IDEMPOTENCY_CONFLICT"
    )


@dataclass(frozen=True)
class _WalletSpec:
    """Where one wallet kind lives: wallet table / model, owner column, txn model."""

    table: str
    wallet_model: type
    wallet_pk: str
    owner_column: str
    txn_model: type
    # kitchen and partner wallets keep running totals; the customer wallet does not
    has_totals: bool
    ensure_sql: object = field(init=False, repr=False)

    def __post_init__(self):
        cols = ", total_earned, total_withdrawn" if self.has_totals else ""
        vals = ", 0, 0" if self.has_totals else ""
        object.__setattr__(self, "ensure_sql", text(
            f"INSERT INTO {self.table} ({self.wallet_pk}, {self.owner_column}, balance{cols}) "
            f"VALUES (gen_random_uuid(), :owner, 0{vals}) ON CONFLICT ({self.owner_column}) DO NOTHING"
        ))


_CUSTOMER = _WalletSpec(
    table="subscription.wallets", wallet_model=Wallet, wallet_pk="wallet_id",
    owner_column="user_reference_id", txn_model=WalletTransaction, has_totals=False,
)
_PROVIDER = _WalletSpec(
    table="provider.provider_wallets", wallet_model=ProviderWallet, wallet_pk="provider_wallet_id",
    owner_column="provider_reference_id", txn_model=ProviderWalletTransaction, has_totals=True,
)
_DELIVERY = _WalletSpec(
    table="delivery.delivery_boy_wallets", wallet_model=DeliveryBoyWallet, wallet_pk="delivery_boy_wallet_id",
    owner_column="delivery_boy_reference_id", txn_model=DeliveryBoyWalletTransaction, has_totals=True,
)


# for reconciliation and reports
WALLET_SPECS = {"customer": _CUSTOMER, "kitchen": _PROVIDER, "delivery_partner": _DELIVERY}


def _lock(db: Session, spec: _WalletSpec, owner_id):
    """Create the wallet if it is missing, then lock its row (SELECT ... FOR UPDATE)."""
    db.execute(spec.ensure_sql, {"owner": str(owner_id)})
    return (
        db.query(spec.wallet_model)
        .filter(getattr(spec.wallet_model, spec.owner_column) == owner_id)
        .populate_existing()
        .with_for_update()
        .one()
    )


def _find_txn(db: Session, spec: _WalletSpec, idempotency_key: str):
    return db.query(spec.txn_model).filter(spec.txn_model.idempotency_key == idempotency_key).first()


def _post(
    db: Session,
    spec: _WalletSpec,
    owner_id,
    *,
    type: str,
    amount,
    reason: str,
    idempotency_key: str,
    reference_type: str | None,
    reference_id,
    description: str | None,
    wallet=None,
    counts_as_earning: bool = False,
    counts_as_withdrawal: bool = False,
    extra: dict | None = None,
):
    if type not in ("credit", "debit"):
        raise ValueError("type must be credit or debit")
    amount = _positive(amount)
    wallet = wallet or _lock(db, spec, owner_id)

    existing = _find_txn(db, spec, idempotency_key)
    if existing:
        if existing.type != type or money(existing.amount) != amount:
            raise _idempotency_conflict()
        return existing

    before = money(wallet.balance)
    if type == "debit":
        if before < amount:
            raise InsufficientBalance(amount, before)
        after = before - amount
    else:
        after = before + amount

    wallet.balance = after
    if spec.has_totals and counts_as_earning:
        wallet.total_earned = money(wallet.total_earned) + amount
    if spec.has_totals and counts_as_withdrawal:
        wallet.total_withdrawn = money(wallet.total_withdrawn) + amount

    txn = spec.txn_model(
        wallet_reference_id=getattr(wallet, spec.wallet_pk),
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
        **{spec.owner_column: owner_id},
        **(extra or {}),
    )
    db.add(txn)
    db.flush()
    return txn


# ── Customer wallet ───────────────────────────────────────────

def lock_customer_wallet(db: Session, user_id) -> Wallet:
    return _lock(db, _CUSTOMER, user_id)


def customer_balance(db: Session, user_id) -> Decimal:
    """Balance for display and quotes: no row lock, and no wallet is created."""
    balance = db.query(Wallet.balance).filter(Wallet.user_reference_id == user_id).scalar()
    return money(balance if balance is not None else ZERO)


def customer_txn_exists(db: Session, idempotency_key: str) -> WalletTransaction | None:
    return _find_txn(db, _CUSTOMER, idempotency_key)


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
    return _post(
        db, _CUSTOMER, user_id,
        type=type, amount=amount, reason=reason, idempotency_key=idempotency_key,
        reference_type=reference_type, reference_id=reference_id, description=description,
        wallet=wallet, extra={"created_by": created_by},
    )


def delivery_txn_exists(db: Session, idempotency_key: str) -> DeliveryBoyWalletTransaction | None:
    return _find_txn(db, _DELIVERY, idempotency_key)


# ── Kitchen wallet ────────────────────────────────────────────

def lock_provider_wallet(db: Session, provider_id) -> ProviderWallet:
    return _lock(db, _PROVIDER, provider_id)


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
    return _post(
        db, _PROVIDER, provider_id,
        type=type, amount=amount, reason=reason, idempotency_key=idempotency_key,
        reference_type=reference_type, reference_id=reference_id, description=description,
        counts_as_earning=counts_as_earning, counts_as_withdrawal=counts_as_withdrawal,
    )


# ── Delivery partner wallet ───────────────────────────────────

def lock_delivery_wallet(db: Session, delivery_boy_id) -> DeliveryBoyWallet:
    return _lock(db, _DELIVERY, delivery_boy_id)


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
    return _post(
        db, _DELIVERY, delivery_boy_id,
        type=type, amount=amount, reason=reason, idempotency_key=idempotency_key,
        reference_type=reference_type, reference_id=reference_id, description=description,
        counts_as_earning=counts_as_earning, counts_as_withdrawal=counts_as_withdrawal,
    )


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
    if direction not in ("credit", "debit"):
        raise ValueError("direction must be credit or debit")
    amount = money(amount)
    if amount <= ZERO:
        return None
    existing = (
        db.query(PlatformLedgerEntry)
        .filter(PlatformLedgerEntry.idempotency_key == idempotency_key)
        .first()
    )
    if existing:
        if existing.direction != direction or money(existing.amount) != amount:
            raise _idempotency_conflict()
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
