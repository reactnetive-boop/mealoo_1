"""The shared wallet poster: balances, idempotency and validation."""

import uuid
from decimal import Decimal

import pytest

from app.core.errors import DomainError
from app.domain import ledger
from tests import factories as f


def test_customer_credit_debit_and_balance_snapshot(db):
    user, _, _ = f.customer(db)
    credit = ledger.post_customer(db, user.user_id, type="credit", amount="100", reason="adjustment",
                                  idempotency_key="t:c1")
    debit = ledger.post_customer(db, user.user_id, type="debit", amount="40", reason="adjustment",
                                 idempotency_key="t:d1")
    db.commit()
    assert (credit.balance_before, credit.balance_after) == (Decimal("0.00"), Decimal("100.00"))
    assert (debit.balance_before, debit.balance_after) == (Decimal("100.00"), Decimal("60.00"))
    assert ledger.lock_customer_wallet(db, user.user_id).balance == Decimal("60.00")


def test_debit_cannot_overdraw(db):
    user, _, _ = f.customer(db, balance="10")
    with pytest.raises(ledger.InsufficientBalance) as err:
        ledger.post_customer(db, user.user_id, type="debit", amount="10.01", reason="adjustment",
                             idempotency_key="t:over")
    assert err.value.code == "INSUFFICIENT_BALANCE"


def test_same_key_same_movement_is_a_no_op(db):
    user, _, _ = f.customer(db)
    first = ledger.post_customer(db, user.user_id, type="credit", amount="50", reason="adjustment",
                                 idempotency_key="t:once")
    again = ledger.post_customer(db, user.user_id, type="credit", amount="50.00", reason="adjustment",
                                 idempotency_key="t:once")
    db.commit()
    assert again.wallet_transaction_id == first.wallet_transaction_id
    assert ledger.lock_customer_wallet(db, user.user_id).balance == Decimal("50.00")


@pytest.mark.parametrize("type_, amount", [("credit", "51"), ("debit", "50")])
def test_same_key_different_movement_is_refused(db, type_, amount):
    user, _, _ = f.customer(db, balance="100")
    ledger.post_customer(db, user.user_id, type="credit", amount="50", reason="adjustment",
                         idempotency_key="t:k")
    with pytest.raises(DomainError) as err:
        ledger.post_customer(db, user.user_id, type=type_, amount=amount, reason="adjustment",
                             idempotency_key="t:k")
    assert err.value.status_code == 409
    assert err.value.code == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("post", ["post_provider", "post_delivery"])
def test_kitchen_and_partner_wallets_validate_type(db, post):
    kitchen, _ = f.provider(db)
    boy, _ = f.delivery_boy(db, kitchen=kitchen)
    owner = kitchen.provider_id if post == "post_provider" else boy.delivery_boy_id
    with pytest.raises(ValueError):
        getattr(ledger, post)(db, owner, type="refund", amount="5", reason="x", idempotency_key="t:bad")


def test_kitchen_wallet_keeps_running_totals(db):
    kitchen, _ = f.provider(db)
    ledger.post_provider(db, kitchen.provider_id, type="credit", amount="300", reason="order_delivered",
                         idempotency_key="t:e1", counts_as_earning=True)
    ledger.post_provider(db, kitchen.provider_id, type="debit", amount="120", reason="withdrawal",
                         idempotency_key="t:w1", counts_as_withdrawal=True)
    db.commit()
    wallet = ledger.lock_provider_wallet(db, kitchen.provider_id)
    assert (wallet.balance, wallet.total_earned, wallet.total_withdrawn) == (
        Decimal("180.00"), Decimal("300.00"), Decimal("120.00"))


def test_amount_must_be_positive(db):
    boy, _ = f.delivery_boy(db)
    with pytest.raises(DomainError):
        ledger.post_delivery(db, boy.delivery_boy_id, type="credit", amount="0", reason="x",
                             idempotency_key="t:zero")


REF = uuid.uuid4()


def test_platform_ledger_skips_zero_and_refuses_mismatched_replay(db):
    assert ledger.post_platform(db, entry_type="commission", direction="credit", amount="0",
                                reference_type="order", reference_id=REF, idempotency_key="p:0") is None
    ledger.post_platform(db, entry_type="commission", direction="credit", amount="12",
                         reference_type="order", reference_id=REF, idempotency_key="p:1")
    with pytest.raises(DomainError):
        ledger.post_platform(db, entry_type="commission", direction="debit", amount="12",
                             reference_type="order", reference_id=REF, idempotency_key="p:1")
    with pytest.raises(ValueError):
        ledger.post_platform(db, entry_type="commission", direction="sideways", amount="1",
                             reference_type="order", reference_id=REF, idempotency_key="p:2")
