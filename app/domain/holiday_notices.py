"""
Notices about kitchen holidays, with a log and safe retries.

queue() writes a provider.holiday_notices row inside the caller's
transaction, next to the business change it reports (a new request, a
decision, refunds and skips, a schedule change). Nothing is sent for work
that did not commit. deliver() then hands each pending row to the in-app
notification of its audience (and the phone push), one row per transaction:

  * a failure marks only that row 'failed' (attempts + 1, last error) and is
    retried by the holiday_retry job - from the stored text alone, so a
    refund, skip credit or schedule change is never run a second time;
  * dedupe_key is unique, so the same event never notifies anyone twice,
    however often the work around it is retried.
"""

import logging
import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.domain import notify
from app.models.admin_notification_model import AdminNotification
from app.models.admin_user_model import AdminUser
from app.models.vendor_holiday_model import HolidayNotice

logger = logging.getLogger("app.holidays")

MAX_ATTEMPTS = 5
AUDIENCES = ("admin", "provider", "customer", "delivery_boy")


def queue(db: Session, audience: str, recipient_id, type: str, title: str, body: str, data: dict | None = None,
          *, dedupe_key: str, request_id=None, holiday_id=None) -> None:
    """Log one notice to send once the caller's transaction commits (a repeat key is ignored)."""
    if audience not in AUDIENCES:
        raise ValueError(f"unknown audience {audience}")
    if audience != "admin" and recipient_id is None:
        return
    db.execute(
        pg_insert(HolidayNotice).values(
            holiday_notice_id=uuid.uuid4(),
            request_reference_id=request_id,
            vendor_holiday_reference_id=holiday_id,
            audience=audience,
            recipient_id=recipient_id,
            type=type,
            title=title[:150],
            body=body,
            data=_json(data or {}),
            dedupe_key=dedupe_key[:160],
            status="pending",
            attempts=0,
        ).on_conflict_do_nothing(constraint="uq_holiday_notices_dedupe")
    )


def _json(data: dict) -> dict:
    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in data.items()}


def _send(db: Session, n: HolidayNotice) -> None:
    data = {**(n.data or {}), "holiday_notice_id": str(n.holiday_notice_id)}
    if n.audience == "customer":
        notify.customer(db, n.recipient_id, n.type, n.title, n.body, data, dedupe_key=f"holiday_notice:{n.dedupe_key}"[:160])
    elif n.audience == "provider":
        notify.kitchen(db, n.recipient_id, n.type, n.title, n.body, data, dedupe_key=f"holiday_notice:{n.dedupe_key}"[:160])
    elif n.audience == "delivery_boy":
        notify.delivery_partner(db, n.recipient_id, n.type, n.title, n.body, data)
    else:
        admins = db.query(AdminUser.admin_user_id).filter(AdminUser.is_active == True).all()  # noqa: E712
        for (admin_id,) in admins:
            db.execute(
                pg_insert(AdminNotification).values(
                    admin_notification_id=uuid.uuid4(), admin_user_reference_id=admin_id, type=n.type,
                    title=n.title[:150], body=n.body, data=data,
                    dedupe_key=f"{n.dedupe_key}:{admin_id}"[:200], is_read=False,
                ).on_conflict_do_nothing(constraint="uq_admin_notifications_dedupe")
            )


def deliver(db: Session, *, request_id=None, holiday_id=None, ids=None, retry_failed: bool = False,
            limit: int = 500) -> dict:
    """
    Send pending notices (and, with retry_failed, the failed ones that still
    have attempts left - the retry job and an admin's retry); each one
    commits on its own.
    """
    q = db.query(HolidayNotice.holiday_notice_id).filter(
        HolidayNotice.status.in_(("pending", "failed") if retry_failed else ("pending",)),
        HolidayNotice.attempts < MAX_ATTEMPTS,
    )
    if request_id is not None:
        q = q.filter(HolidayNotice.request_reference_id == request_id)
    if holiday_id is not None:
        q = q.filter(HolidayNotice.vendor_holiday_reference_id == holiday_id)
    if ids is not None:
        q = q.filter(HolidayNotice.holiday_notice_id.in_(list(ids)))
    todo = [nid for (nid,) in q.order_by(HolidayNotice.created_at).limit(limit).all()]
    db.commit()
    sent = failed = 0
    for nid in todo:
        n = db.query(HolidayNotice).filter(
            HolidayNotice.holiday_notice_id == nid
        ).with_for_update(skip_locked=True).populate_existing().first()
        if n is None or n.status == "sent":
            db.rollback()
            continue
        try:
            _send(db, n)
            n.status = "sent"
            n.attempts = (n.attempts or 0) + 1
            n.sent_at = now_utc()
            n.last_error = None
            db.commit()
            sent += 1
        except Exception as exc:  # only the notice failed; the change it reports is committed
            db.rollback()  # also drops the queued push
            logger.warning("holiday notice %s failed: %s", nid, exc)
            n = db.query(HolidayNotice).filter(HolidayNotice.holiday_notice_id == nid).one()
            n.status = "failed"
            n.attempts = (n.attempts or 0) + 1
            n.last_error = str(exc)[:1000]
            db.commit()
            failed += 1
    return {"sent": sent, "failed": failed}


def view(n: HolidayNotice) -> dict:
    return {
        "notice_id": n.holiday_notice_id,
        "audience": n.audience,
        "recipient_id": n.recipient_id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "status": n.status,
        "attempts": n.attempts,
        "last_error": n.last_error,
        "created_at": n.created_at,
        "sent_at": n.sent_at,
    }
