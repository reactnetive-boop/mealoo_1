"""
Push notifications (Expo push service) for the three mobile apps.

Every in-app notification written through app.domain.notify is also queued as
a push for the owner's devices. Pushes are sent only AFTER the database
transaction commits (a rolled-back action never buzzes a phone), from a
background thread so the request does not wait for Expo.

PUSH_PROVIDER=expo sends through https://exp.host (EXPO_ACCESS_TOKEN is
optional, needed when the Expo project enforces push security); "none"
disables sending (tests, or before the apps register tokens). Tokens Expo
reports as DeviceNotRegistered are deleted.
"""

import logging
import threading

import httpx
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import EXPO_ACCESS_TOKEN, PUSH_PROVIDER

logger = logging.getLogger("app.push")

EXPO_URL = "https://exp.host/--/api/v2/push/send"
BATCH = 100
_transport = None   # tests inject an httpx.MockTransport
_sync = False       # tests send inline instead of on a thread
_PENDING = "pending_push"


def queue(db: Session, owner_type: str, owner_id, title: str, body: str, data: dict | None = None) -> None:
    """Remember a push for this session's commit."""
    if PUSH_PROVIDER == "none" or owner_id is None:
        return
    db.info.setdefault(_PENDING, []).append((owner_type, str(owner_id), title, body, data or {}))


@event.listens_for(Session, "after_rollback")
def _discard(session: Session) -> None:
    session.info.pop(_PENDING, None)


@event.listens_for(Session, "after_commit")
def _flush(session: Session) -> None:
    pending = session.info.pop(_PENDING, None)
    if not pending:
        return
    if _sync:
        _send(pending)
    else:
        threading.Thread(target=_send, args=(pending,), name="push-sender", daemon=True).start()


def _send(pending: list) -> None:
    # own session: the caller's transaction is finished
    from app.core.database import SessionLocal
    from app.models.device_push_token_model import DevicePushToken

    db = SessionLocal()
    try:
        owners = {(t, o) for t, o, *_ in pending}
        tokens: dict = {}
        for owner_type, owner_id in owners:
            rows = db.query(DevicePushToken.token).filter(
                DevicePushToken.owner_type == owner_type, DevicePushToken.owner_id == owner_id
            ).all()
            tokens[(owner_type, owner_id)] = [r[0] for r in rows]

        messages = [
            {"to": token, "title": title, "body": body, "data": data, "sound": "default", "priority": "high"}
            for owner_type, owner_id, title, body, data in pending
            for token in tokens[(owner_type, owner_id)]
        ]
        dead = []
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if EXPO_ACCESS_TOKEN:
            headers["Authorization"] = f"Bearer {EXPO_ACCESS_TOKEN}"
        with httpx.Client(timeout=10, transport=_transport) as client:
            for start in range(0, len(messages), BATCH):
                batch = messages[start:start + BATCH]
                r = client.post(EXPO_URL, json=batch, headers=headers)
                if r.status_code >= 400:
                    logger.warning("expo push rejected a batch: %s", r.status_code)
                    continue
                for message, ticket in zip(batch, r.json().get("data", [])):
                    if ticket.get("status") == "error" and (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                        dead.append(message["to"])
        if dead:
            db.query(DevicePushToken).filter(DevicePushToken.token.in_(dead)).delete(synchronize_session=False)
            db.commit()
    except Exception:
        logger.exception("push sending failed")
        db.rollback()
    finally:
        db.close()
