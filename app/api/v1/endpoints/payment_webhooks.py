"""Payment gateway callbacks (server to server, no user token)."""

from fastapi import APIRouter, Depends, Header, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.razorpay_service import RazorpayService

router = APIRouter()


@router.post("/payments/razorpay/webhook", include_in_schema=False)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(None),
    db: Session = Depends(get_db),
):
    # the signature covers the exact raw body
    raw = await request.body()
    return await run_in_threadpool(RazorpayService.webhook, db, raw, x_razorpay_signature)
