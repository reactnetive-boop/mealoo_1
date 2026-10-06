"""
Sending OTPs by SMS.

SMS_PROVIDER picks the gateway:
  * console  - development: the OTP is only logged (and echoed in the API
               response when OTP_ECHO_IN_RESPONSE is on). Never in production.
  * msg91    - MSG91 OTP API (DLT-registered template): MSG91_AUTH_KEY,
               MSG91_TEMPLATE_ID.
  * twilio   - Twilio Messages API: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
               TWILIO_FROM.
  * none     - nothing is sent (production without a gateway: registration
               and password reset cannot complete, see validate_settings).

Numbers are stored as 10-digit Indian mobiles; the gateways get +91.
A failed send raises DomainError(502) so the app can tell the user to retry;
the code itself is never logged outside the console provider.
"""

import logging

import httpx

from app.core.config import (
    MSG91_AUTH_KEY,
    MSG91_TEMPLATE_ID,
    SMS_PROVIDER,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM,
)
from app.core.errors import DomainError

logger = logging.getLogger("app.sms")

TIMEOUT_SECONDS = 8
_transport = None  # tests inject an httpx.MockTransport


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, transport=_transport)


def _e164(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"+91{digits}" if len(digits) == 10 else f"+{digits}"


def _failed(provider: str, detail) -> DomainError:
    logger.error("sms send failed provider=%s detail=%s", provider, detail)
    return DomainError("We could not send the OTP right now. Please try again in a minute.", 502, code="SMS_FAILED")


def _msg91(phone: str, code: str) -> None:
    try:
        with _client() as c:
            r = c.post(
                "https://control.msg91.com/api/v5/otp",
                params={"template_id": MSG91_TEMPLATE_ID, "mobile": _e164(phone).lstrip("+"), "otp": code},
                headers={"authkey": MSG91_AUTH_KEY or ""},
            )
    except httpx.HTTPError as exc:
        raise _failed("msg91", type(exc).__name__) from None
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 400 or body.get("type") == "error":
        raise _failed("msg91", f"{r.status_code} {body.get('message')}")


def _twilio(phone: str, code: str, purpose: str) -> None:
    text = f"{code} is your Orleeno {'password reset' if purpose == 'password_reset' else 'verification'} code. " \
           "It expires in a few minutes. Do not share it with anyone."
    try:
        with _client() as c:
            r = c.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
                data={"To": _e164(phone), "From": TWILIO_FROM or "", "Body": text},
                auth=(TWILIO_ACCOUNT_SID or "", TWILIO_AUTH_TOKEN or ""),
            )
    except httpx.HTTPError as exc:
        raise _failed("twilio", type(exc).__name__) from None
    if r.status_code >= 400:
        raise _failed("twilio", r.status_code)


def send_otp(phone: str, code: str, purpose: str) -> None:
    """Deliver an OTP. Raises DomainError(502) if the gateway refuses or is unreachable."""
    provider = SMS_PROVIDER
    if provider == "console":
        logger.info("OTP for ...%s (%s): %s", phone[-4:], purpose, code)
    elif provider == "msg91":
        _msg91(phone, code)
    elif provider == "twilio":
        _twilio(phone, code, purpose)
    else:
        logger.warning("SMS_PROVIDER=%s: OTP for ...%s was not sent", provider, phone[-4:])
