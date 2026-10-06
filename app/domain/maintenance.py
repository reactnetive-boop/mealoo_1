"""
Book-keeping checks and data retention.

reconcile()      read-only health report of the money and the order pipeline:
                 every wallet balance must equal the sum of its ledger
                 movements and its last transaction's balance_after, no
                 balance may be negative, every delivered order must be
                 settled exactly once, and nothing may be stuck (meals in a
                 partner's hands from earlier days, withdrawals waiting too
                 long). Run nightly (problems are logged at ERROR so error
                 reporting alerts) and on demand from the admin panel.

purge()          deletes what no longer has a purpose: used / expired OTP
                 rows, notifications that were read long ago and, only when
                 a retention period is configured, old audit-log partitions.
                 Ledgers, orders and payments are never purged.

ensure_audit_partitions()
                 keeps monthly partitions of master.audit_logs ready a few
                 months ahead, so old months can be dropped cheaply.
"""

from datetime import date, timedelta

from sqlalchemy import and_, case, exists, func, or_, text
from sqlalchemy.orm import Session

from app.core.clock import now_utc, today_local
from app.core.config import (
    AUDIT_LOG_RETENTION_MONTHS,
    NOTIFICATION_RETENTION_DAYS,
    OTP_LOG_RETENTION_DAYS,
    PAYOUT_PENDING_ALERT_DAYS,
)
from app.domain import ledger
from app.domain.status import IN_HAND_STATUSES
from app.models.delivery_boy_notification_model import DeliveryBoyNotification
from app.models.delivery_boy_otp_log_model import DeliveryBoyOTPLog
from app.models.extra_order_model import ExtraOrder
from app.models.notification_model import Notification
from app.models.order_model import Order
from app.models.otp_log_model import OTPLog
from app.models.payout_request_model import PayoutRequest
from app.models.platform_ledger_model import PlatformLedgerEntry
from app.models.provider_notification_model import ProviderNotification
from app.models.user_otp_log_model import UserOTPLog

SAMPLE = 20  # ids listed per problem; counts are always complete


# ── Reconciliation ────────────────────────────────────────────

def _wallet_problems(db: Session, spec) -> dict:
    w, t = spec.wallet_model, spec.txn_model
    pk = getattr(w, spec.wallet_pk)
    signed = case((t.type == "credit", t.amount), else_=-t.amount)
    ledger_sum = func.coalesce(func.sum(signed), 0)

    drift = (
        db.query(pk, w.balance, ledger_sum.label("ledger"))
        .outerjoin(t, t.wallet_reference_id == pk)
        .group_by(pk, w.balance)
        .having(w.balance != ledger_sum)
        .all()
    )

    latest = (
        db.query(t.wallet_reference_id, func.max(t.created_at).label("at"))
        .group_by(t.wallet_reference_id)
        .subquery()
    )
    # several movements can share the latest timestamp: one of them must match
    last_mismatch = (
        db.query(pk)
        .join(latest, latest.c.wallet_reference_id == pk)
        .filter(~exists().where(and_(
            t.wallet_reference_id == pk, t.created_at == latest.c.at, t.balance_after == w.balance,
        )))
        .all()
    )
    negative = db.query(pk).filter(w.balance < 0).all()

    return {
        "wallets": db.query(func.count(pk)).scalar(),
        "balance_not_equal_ledger": {
            "count": len(drift),
            "sample": [{"wallet_id": str(r[0]), "balance": str(r[1]), "ledger": str(r[2])} for r in drift[:SAMPLE]],
        },
        "balance_not_equal_last_transaction": {
            "count": len(last_mismatch), "sample": [str(r[0]) for r in last_mismatch[:SAMPLE]],
        },
        "negative_balance": {"count": len(negative), "sample": [str(r[0]) for r in negative[:SAMPLE]]},
    }


def _ids(rows) -> dict:
    return {"count": len(rows), "sample": [str(r[0]) for r in rows[:SAMPLE]]}


def _settlement_problems(db: Session) -> dict:
    unsettled_meals = db.query(Order.order_id).filter(
        Order.status == "delivered", Order.settled_at.is_(None)
    ).all()
    unsettled_extra = db.query(ExtraOrder.extra_order_id).filter(
        ExtraOrder.status == "delivered", ExtraOrder.settled_at.is_(None)
    ).all()
    settled_not_delivered = db.query(Order.order_id).filter(
        Order.settled_at.isnot(None), Order.status.notin_(("delivered", "delivery_failed", "cancelled"))
    ).all()
    return {
        "delivered_not_settled": _ids(unsettled_meals),
        "one_time_delivered_not_settled": _ids(unsettled_extra),
        "settled_but_not_delivered": _ids(settled_not_delivered),
    }


def _pipeline_problems(db: Session) -> dict:
    today = today_local()
    stuck_meals = db.query(Order.order_id).filter(
        Order.status.in_(IN_HAND_STATUSES), Order.order_date < today
    ).all()
    stuck_extra = db.query(ExtraOrder.extra_order_id).filter(
        ExtraOrder.status.in_(IN_HAND_STATUSES), ExtraOrder.delivery_date < today
    ).all()
    old_payouts = db.query(PayoutRequest.payout_request_id).filter(
        PayoutRequest.status == "pending",
        PayoutRequest.requested_at < now_utc() - timedelta(days=PAYOUT_PENDING_ALERT_DAYS),
    ).all()
    return {
        "in_partner_hands_from_earlier_days": _ids(stuck_meals + stuck_extra),
        "withdrawals_pending_too_long": _ids(old_payouts),
    }


def _platform_totals(db: Session) -> dict:
    signed = case((PlatformLedgerEntry.direction == "credit", PlatformLedgerEntry.amount),
                  else_=-PlatformLedgerEntry.amount)
    rows = (
        db.query(PlatformLedgerEntry.entry_type, func.sum(signed))
        .group_by(PlatformLedgerEntry.entry_type)
        .all()
    )
    totals = {entry_type: str(amount) for entry_type, amount in rows}
    totals["net"] = str(sum((amount for _, amount in rows), 0))
    return totals


def reconcile(db: Session) -> dict:
    wallets = {kind: _wallet_problems(db, spec) for kind, spec in ledger.WALLET_SPECS.items()}
    settlement = _settlement_problems(db)
    pipeline = _pipeline_problems(db)

    issues = sum(
        check["count"] for kind in wallets.values() for name, check in kind.items() if name != "wallets"
    ) + sum(c["count"] for c in settlement.values()) + sum(c["count"] for c in pipeline.values())
    money_issues = issues - sum(c["count"] for c in pipeline.values())
    return {
        "checked_at": now_utc().isoformat(),
        "ok": issues == 0,
        "money_issues": money_issues,
        "operational_issues": issues - money_issues,
        "wallets": wallets,
        "settlement": settlement,
        "pipeline": pipeline,
        "platform_ledger": _platform_totals(db),
    }


# ── Retention ─────────────────────────────────────────────────

def _month_start(d: date, add: int = 0) -> date:
    index = d.year * 12 + (d.month - 1) + add
    return date(index // 12, index % 12 + 1, 1)


def ensure_audit_partitions(db: Session, months_ahead: int = 3) -> list[str]:
    """
    Create monthly partitions from next month on. The current month stays in
    the default partition: a partition cannot be added for a range that the
    default partition already holds rows for.
    """
    today = today_local()
    created = []
    for offset in range(1, months_ahead + 1):
        start, end = _month_start(today, offset), _month_start(today, offset + 1)
        name = f"audit_logs_y{start.year}m{start.month:02d}"
        exists = db.execute(text(
            "SELECT 1 FROM pg_tables WHERE schemaname = 'master' AND tablename = :n"
        ), {"n": name}).first()
        if exists:
            continue
        db.execute(text(
            f"CREATE TABLE master.{name} PARTITION OF master.audit_logs "
            f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
        ))
        created.append(name)
    return created


def _purge_audit(db: Session) -> int:
    if AUDIT_LOG_RETENTION_MONTHS <= 0:
        return 0  # keep forever unless a retention period is configured
    cutoff = _month_start(today_local(), -AUDIT_LOG_RETENTION_MONTHS)
    dropped = 0
    for (name,) in db.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'master' AND tablename ~ '^audit_logs_y[0-9]{4}m[0-9]{2}$'"
    )).all():
        year, month = int(name[12:16]), int(name[17:19])
        if _month_start(date(year, month, 1), 1) <= cutoff:
            db.execute(text(f"DROP TABLE master.{name}"))
            dropped += 1
    db.execute(text("DELETE FROM master.audit_logs_default WHERE created_at < :c"), {"c": cutoff})
    return dropped


def purge(db: Session) -> dict:
    now = now_utc()
    otp_cutoff = now - timedelta(days=OTP_LOG_RETENTION_DAYS)
    note_cutoff = now - timedelta(days=NOTIFICATION_RETENTION_DAYS)
    result = {}

    for label, model in (("customer_otps", UserOTPLog), ("kitchen_otps", OTPLog), ("partner_otps", DeliveryBoyOTPLog)):
        result[label] = (
            db.query(model)
            .filter(model.created_at < otp_cutoff, or_(model.expires_at < now, model.expires_at.is_(None)))
            .delete(synchronize_session=False)
        )

    for label, model in (
        ("customer_notifications", Notification),
        ("kitchen_notifications", ProviderNotification),
        ("partner_notifications", DeliveryBoyNotification),
    ):
        result[label] = (
            db.query(model)
            .filter(model.created_at < note_cutoff, model.is_read == True)  # noqa: E712
            .delete(synchronize_session=False)
        )

    result["audit_partitions_created"] = len(ensure_audit_partitions(db))
    result["audit_partitions_dropped"] = _purge_audit(db)
    return result
