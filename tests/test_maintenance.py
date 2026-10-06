"""Nightly reconciliation and data retention (BE-D4, BE-D5)."""

from datetime import timedelta

from sqlalchemy import text

from app.core.clock import now_utc, today_local
from app.domain import maintenance
from app.models.notification_model import Notification
from app.models.order_model import Order
from app.models.user_otp_log_model import UserOTPLog
from app.models.wallet_model import Wallet
from app.schedulers import jobs
from tests import factories as f

S = "/api/v1/user/subscription"
M = "/api/v1/admin/maintenance"


def _subscribe(client, w):
    r = client.post(S, headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert r.status_code == 200, r.text
    return r.json()["subscription_id"]


def test_clean_books_reconcile(client, db):
    w = f.world(db)
    _subscribe(client, w)
    report = maintenance.reconcile(db)
    assert report["ok"], report
    assert report["wallets"]["customer"]["wallets"] == 1


def test_tampered_balance_is_reported(client, db):
    w = f.world(db, balance="500")
    db.query(Wallet).filter(Wallet.user_reference_id == w["user"].user_id).update({"balance": 999})
    db.commit()
    report = maintenance.reconcile(db)
    assert not report["ok"]
    customer = report["wallets"]["customer"]
    assert customer["balance_not_equal_ledger"]["count"] == 1
    assert customer["balance_not_equal_last_transaction"]["count"] == 1
    assert report["money_issues"] == 2


def test_unsettled_and_stuck_orders_are_reported(client, db):
    w = f.world(db)
    sub_id = _subscribe(client, w)
    meals = db.query(Order).filter(Order.subscription_reference_id == sub_id).order_by(Order.order_date).all()
    meals[0].status = "delivered"                      # delivered but never settled
    meals[1].status = "picked_up"                      # still in the partner's hands ...
    meals[1].order_date = today_local() - timedelta(days=1)  # ... since yesterday
    db.commit()
    report = maintenance.reconcile(db)
    assert report["settlement"]["delivered_not_settled"]["count"] == 1
    assert report["pipeline"]["in_partner_hands_from_earlier_days"]["count"] == 1
    assert report["operational_issues"] == 1


def test_purge_keeps_what_is_still_useful(db):
    user, _, _ = f.customer(db)
    old = now_utc() - timedelta(days=200)
    db.add_all([
        UserOTPLog(contact="9000000001", channel="sms", otp_hash="x", purpose="registration", attempts=0, is_used=True,
                   expires_at=old, created_at=old),
        UserOTPLog(contact="9000000002", channel="sms", otp_hash="x", purpose="registration", attempts=0, is_used=False,
                   expires_at=now_utc() + timedelta(minutes=5), created_at=now_utc()),
        Notification(user_reference_id=user.user_id, type="x", title="old read", body="b", is_read=True, created_at=old),
        Notification(user_reference_id=user.user_id, type="x", title="old unread", body="b", is_read=False, created_at=old),
        Notification(user_reference_id=user.user_id, type="x", title="new read", body="b", is_read=True),
    ])
    db.commit()
    result = maintenance.purge(db)
    db.commit()
    assert result["customer_otps"] == 1 and result["customer_notifications"] == 1
    assert db.query(UserOTPLog).count() == 1
    assert {n.title for n in db.query(Notification).all()} == {"old unread", "new read"}


def test_audit_partitions_are_prepared_once(db):
    maintenance.ensure_audit_partitions(db)
    db.commit()
    assert maintenance.ensure_audit_partitions(db) == []
    names = {r[0] for r in db.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'master' AND tablename LIKE 'audit_logs_y%'"
    ))}
    assert {"audit_logs_y2026m11", "audit_logs_y2026m12", "audit_logs_y2027m01"} <= names


def test_nightly_job_runs_both(db, caplog):
    w = f.world(db, balance="100")
    db.query(Wallet).filter(Wallet.user_reference_id == w["user"].user_id).update({"balance": 1})
    db.commit()
    result = jobs._maintenance(db)
    db.commit()
    assert result["reconciliation_ok"] is False
    assert any("reconciliation" in r.message for r in caplog.records if r.levelname == "ERROR")


def test_admin_endpoints_are_super_admin_only(client, db):
    _, super_hdr = f.admin(db)
    _, ops_hdr = f.admin(db, role="moderator")
    assert client.get(f"{M}/reconciliation", headers=ops_hdr).status_code == 403
    r = client.get(f"{M}/reconciliation", headers=super_hdr)
    assert r.status_code == 200 and r.json()["ok"] is True
    r = client.post(f"{M}/purge", headers=super_hdr)
    assert r.status_code == 200, r.text
