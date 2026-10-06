"""Push token registration for the customer, kitchen and delivery partner apps."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user, get_delivery_session, get_provider_session
from app.services.push_token_service import PushTokenService

router = APIRouter()


class PushTokenRequest(BaseModel):
    token: str = Field(..., pattern=r"^Expo(nent)?PushToken\[[A-Za-z0-9_-]{10,200}\]$")
    platform: Optional[Literal["android", "ios"]] = None


DOC = "Call after login and whenever Expo gives the app a new token; call DELETE before logout."


@router.post("/user/push-token", tags=["User Notifications"], summary="Enable Push on This Device", description=DOC)
def customer_register(payload: PushTokenRequest, db: Session = Depends(get_db), current=Depends(get_current_user)):
    return PushTokenService.register(db, "customer", current["user_id"], payload.token, payload.platform)


@router.delete("/user/push-token", tags=["User Notifications"], summary="Disable Push on This Device")
def customer_unregister(payload: PushTokenRequest, db: Session = Depends(get_db), current=Depends(get_current_user)):
    return PushTokenService.unregister(db, "customer", current["user_id"], payload.token)


@router.post("/provider/push-token", tags=["Provider Notifications"], summary="Enable Push on This Device", description=DOC)
def kitchen_register(payload: PushTokenRequest, db: Session = Depends(get_db), current=Depends(get_provider_session)):
    return PushTokenService.register(db, "provider", current["provider_id"], payload.token, payload.platform)


@router.delete("/provider/push-token", tags=["Provider Notifications"], summary="Disable Push on This Device")
def kitchen_unregister(payload: PushTokenRequest, db: Session = Depends(get_db), current=Depends(get_provider_session)):
    return PushTokenService.unregister(db, "provider", current["provider_id"], payload.token)


@router.post("/delivery/push-token", tags=["Delivery Notifications"], summary="Enable Push on This Device", description=DOC)
def partner_register(payload: PushTokenRequest, db: Session = Depends(get_db), current=Depends(get_delivery_session)):
    return PushTokenService.register(db, "delivery_boy", current["delivery_boy_id"], payload.token, payload.platform)


@router.delete("/delivery/push-token", tags=["Delivery Notifications"], summary="Disable Push on This Device")
def partner_unregister(payload: PushTokenRequest, db: Session = Depends(get_db), current=Depends(get_delivery_session)):
    return PushTokenService.unregister(db, "delivery_boy", current["delivery_boy_id"], payload.token)
