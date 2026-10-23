"""
In-app notifications written inside the caller's transaction (no commit).
Each one is also sent as a push to the owner's phones once that transaction
commits (app.core.push).
"""

from sqlalchemy.orm import Session

from app.core import push

from app.models.notification_model import Notification
from app.models.delivery_boy_notification_model import DeliveryBoyNotification
from app.models.provider_notification_model import ProviderNotification


def customer(db: Session, user_id, type: str, title: str, body: str, data: dict | None = None) -> None:
    db.add(Notification(user_reference_id=user_id, type=type, title=title, body=body, data=data))
    push.queue(db, "customer", user_id, title, body, {**(data or {}), "type": type})


def delivery_partner(db: Session, delivery_boy_id, type: str, title: str, body: str, data: dict | None = None) -> None:
    if delivery_boy_id is None:
        return
    db.add(
        DeliveryBoyNotification(
            delivery_boy_reference_id=delivery_boy_id, type=type, title=title, body=body, data=data
        )
    )
    push.queue(db, "delivery_boy", delivery_boy_id, title, body, {**(data or {}), "type": type})


def kitchen(db: Session, provider_id, type: str, title: str, body: str, data: dict | None = None,
            dedupe_key: str | None = None) -> None:
    """dedupe_key: one notice per business event; a second call with the same key does nothing."""
    if provider_id is None:
        return
    if dedupe_key is not None:
        pending = any(isinstance(o, ProviderNotification) and o.dedupe_key == dedupe_key for o in db.new)
        if pending or db.query(ProviderNotification.provider_notification_id).filter(
            ProviderNotification.dedupe_key == dedupe_key
        ).first() is not None:
            return
    db.add(ProviderNotification(
        provider_reference_id=provider_id, type=type, title=title, body=body, data=data, dedupe_key=dedupe_key,
    ))
    push.queue(db, "provider", provider_id, title, body, {**(data or {}), "type": type})
