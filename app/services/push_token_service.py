"""Register / forget the push token of an app install (see app.core.push)."""

from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.models.device_push_token_model import DevicePushToken


class PushTokenService:

    @staticmethod
    def register(db: Session, owner_type: str, owner_id, token: str, platform: str | None) -> dict:
        row = db.query(DevicePushToken).filter(DevicePushToken.token == token).with_for_update().first()
        if row is None:
            row = DevicePushToken(token=token)
            db.add(row)
        # a phone that changed hands (new login) belongs to the new account only
        row.owner_type = owner_type
        row.owner_id = owner_id
        row.platform = platform
        row.last_seen_at = now_utc()
        db.commit()
        return {"success": True, "message": "Push notifications enabled on this device"}

    @staticmethod
    def unregister(db: Session, owner_type: str, owner_id, token: str) -> dict:
        db.query(DevicePushToken).filter(
            DevicePushToken.token == token,
            DevicePushToken.owner_type == owner_type,
            DevicePushToken.owner_id == owner_id,
        ).delete(synchronize_session=False)
        db.commit()
        return {"success": True, "message": "Push notifications disabled on this device"}
