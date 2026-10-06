"""Kitchen payout details (BE-B6) and bank numbers encrypted at rest (BE-S6)."""

from sqlalchemy import text

from app.core import crypto
from tests import factories as f

W = "/api/v1/provider/wallet"
BANK = {"account_holder_name": "Asha Devi", "account_number": "123456789012", "ifsc_code": "SBIN0001234"}


def test_kitchen_saves_and_reads_its_payout_details(client, db):
    _, hdr = f.provider(db, payout=False)
    assert client.get(f"{W}/payout-details", headers=hdr).json()["ready"] is False

    half = client.put(f"{W}/payout-details", headers=hdr, json={"account_number": "123456789012"})
    assert half.status_code == 400  # a bank account needs holder name and IFSC too

    r = client.put(f"{W}/payout-details", headers=hdr, json=BANK)
    assert r.status_code == 200, r.text
    mine = client.get(f"{W}/payout-details", headers=hdr).json()
    assert mine["ready"] and mine["payout_details"]["account_number"] == "123456789012"


def test_account_numbers_are_encrypted_in_the_database(client, db):
    kitchen, hdr = f.provider(db, payout=False)
    client.put(f"{W}/payout-details", headers=hdr, json=BANK)
    stored = db.execute(text(
        "SELECT account_number FROM provider.provider_payout_details WHERE provider_reference_id = :p"
    ), {"p": kitchen.provider_id}).scalar()
    assert stored.startswith("enc:v1:") and "123456789012" not in stored

    f.delivery_boy(db)
    db.execute(text("UPDATE delivery.delivery_boy_payout_details SET account_number = :n"), {"n": "998877665544"})
    db.commit()
    # rows from before encryption are still readable, and a changed number is stored encrypted
    from app.models.delivery_boy_payout_model import DeliveryBoyPayoutDetails
    row = db.query(DeliveryBoyPayoutDetails).one()
    assert row.account_number == "998877665544"
    row.account_number = "998877665545"
    db.commit()
    raw = db.execute(text("SELECT account_number FROM delivery.delivery_boy_payout_details")).scalar()
    assert crypto.is_encrypted(raw)


def test_admin_sees_masked_list_and_audited_full_reveal(client, db):
    kitchen, hdr = f.provider(db, payout=False)
    client.put(f"{W}/payout-details", headers=hdr, json=BANK)
    _, admin_hdr = f.admin(db)
    _, moderator = f.admin(db, role="moderator")
    url = f"/api/v1/admin/providers/{kitchen.provider_id}/payout-details"
    assert client.get(url, headers=moderator).status_code == 403
    full = client.get(url, headers=admin_hdr).json()
    assert full["payout_details"]["account_number"] == "123456789012"
    from app.models.audit_log_model import AuditLog
    assert db.query(AuditLog).filter(AuditLog.table_name == "provider.provider_payout_details").count() == 1


def test_key_rotation_keeps_old_values_readable(monkeypatch):
    from cryptography.fernet import Fernet, MultiFernet

    old_key, new_key = Fernet.generate_key(), Fernet.generate_key()
    monkeypatch.setattr(crypto, "_cipher", MultiFernet([Fernet(old_key)]))
    token = crypto.encrypt("123456")
    monkeypatch.setattr(crypto, "_cipher", MultiFernet([Fernet(new_key), Fernet(old_key)]))
    assert crypto.decrypt(token) == "123456"
    monkeypatch.setattr(crypto, "_cipher", MultiFernet([Fernet(new_key)]))
    assert crypto.decrypt(token) is None  # unreadable without the old key, never garbage
    assert crypto.encrypt(None) is None and crypto.decrypt("plain") == "plain"


def test_customer_withdraws_wallet_money(client, db):
    from decimal import Decimal

    from app.models.wallet_model import Wallet

    user, _, hdr = f.customer(db, balance="500")
    W2 = "/api/v1/user/wallet"
    r = client.post(f"{W2}/withdraw", headers=hdr, json={"amount": "200"})
    assert r.status_code == 400 and r.json()["code"] == "PAYOUT_DETAILS_MISSING"
    assert client.put(f"{W2}/payout-details", headers=hdr, json={"upi_id": "ravi@okbank"}).status_code == 200
    r = client.post(f"{W2}/withdraw", headers=hdr, json={"amount": "200"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).one().balance == Decimal("300.00")

    _, admin_hdr = f.admin(db)
    req = client.get("/api/v1/admin/payouts", headers=admin_hdr, params={"owner_type": "customer"}).json()["requests"][0]
    assert req["owner_name"] == "Ravi Kumar" and req["destination"]["upi_id"] == "ravi@okbank"
    r = client.put(f"/api/v1/admin/payouts/{req['payout_request_id']}", headers=admin_hdr,
                   json={"action": "rejected", "admin_note": "Use the refund flow"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).one().balance == Decimal("500.00")
    assert client.get(f"{W2}/withdrawals", headers=hdr).json()["requests"][0]["status"] == "rejected"
