"""In-app notifications written inside the caller's transaction (no commit)."""

from sqlalchemy.orm import Session

from app.models.notification_model import Notification
from app.models.delivery_boy_notification_model import DeliveryBoyNotification


def customer(db: Session, user_id, type: str, title: str, body: str, data: dict | None = None) -> None:
    db.add(Notification(user_reference_id=user_id, type=type, title=title, body=body, data=data))


def delivery_partner(db: Session, delivery_boy_id, type: str, title: str, body: str, data: dict | None = None) -> None:
    if delivery_boy_id is None:
        return
    db.add(
        DeliveryBoyNotification(
            delivery_boy_reference_id=delivery_boy_id, type=type, title=title, body=body, data=data
        )
    )
