"""
Audit trail and security event logging.

record_audit() writes to master.audit_logs inside the caller's transaction,
so the audit row commits (or rolls back) together with the change it
describes. security_event() goes to the "security" logger; it must never be
given passwords, OTPs, tokens or other secrets.
"""

import ipaddress
import json
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.audit_log_model import AuditLog

security_logger = logging.getLogger("security")
business_logger = logging.getLogger("business")


def _jsonable(value):
    if value is None:
        return None
    return json.loads(json.dumps(value, default=_default))


def _default(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, uuid.UUID):
        return str(o)
    return str(o)


def record_audit(
    db: Session,
    *,
    table: str,
    record_id=None,
    operation: str = "U",
    old: dict | None = None,
    new: dict | None = None,
    actor_id=None,
    actor_type: str | None = None,
    ip: str | None = None,
) -> None:
    if operation not in ("I", "U", "D"):
        raise ValueError("operation must be I, U or D")

    def _uuid(v):
        if v is None:
            return None
        try:
            return uuid.UUID(str(v))
        except ValueError:
            return None

    try:
        ip = str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        ip = None  # column is INET; proxies / test clients may send non-IP values

    db.add(
        AuditLog(
            table_name=table,
            record_id=_uuid(record_id),
            operation=operation,
            old_data=_jsonable(old),
            new_data=_jsonable(new),
            changed_by=_uuid(actor_id),
            changed_by_type=actor_type,
            ip_address=ip,
        )
    )
    db.flush()


def security_event(event: str, **fields) -> None:
    safe = {k: (str(v) if v is not None else None) for k, v in fields.items()}
    security_logger.warning("%s %s", event, json.dumps(safe, sort_keys=True))


def business_event(event: str, **fields) -> None:
    safe = {k: (str(v) if v is not None else None) for k, v in fields.items()}
    business_logger.info("%s %s", event, json.dumps(safe, sort_keys=True))
