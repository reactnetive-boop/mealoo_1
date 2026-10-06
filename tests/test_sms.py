"""BE-S1: OTPs are delivered through a pluggable SMS gateway."""

import httpx
import pytest

from app.core import sms
from app.core.errors import DomainError

U = "/api/v1/user/auth"


@pytest.fixture
def gateway(monkeypatch):
    calls = []

    def use(provider, status=200, body=None):
        def handler(request: httpx.Request):
            calls.append(request)
            return httpx.Response(status, json=body or {"type": "success"})

        monkeypatch.setattr(sms, "SMS_PROVIDER", provider)
        monkeypatch.setattr(sms, "_transport", httpx.MockTransport(handler))
        monkeypatch.setattr(sms, "MSG91_AUTH_KEY", "msg91-key")
        monkeypatch.setattr(sms, "MSG91_TEMPLATE_ID", "tpl-1")
        monkeypatch.setattr(sms, "TWILIO_ACCOUNT_SID", "AC123")
        monkeypatch.setattr(sms, "TWILIO_AUTH_TOKEN", "secret")
        monkeypatch.setattr(sms, "TWILIO_FROM", "+15550001111")
        return calls

    return use


def test_msg91_request(gateway):
    calls = gateway("msg91")
    sms.send_otp("9876543210", "123456", "registration")
    req = calls[0]
    assert req.url.host == "control.msg91.com"
    assert req.url.params["mobile"] == "919876543210" and req.url.params["otp"] == "123456"
    assert req.headers["authkey"] == "msg91-key"


def test_twilio_request(gateway):
    calls = gateway("twilio")
    sms.send_otp("9876543210", "654321", "password_reset")
    body = calls[0].content.decode()
    assert "To=%2B919876543210" in body and "654321" in body and "password+reset" in body


@pytest.mark.parametrize("provider,status,body", [("msg91", 200, {"type": "error", "message": "bad"}),
                                                  ("msg91", 500, None), ("twilio", 401, None)])
def test_gateway_failure_is_a_retryable_502(gateway, provider, status, body):
    gateway(provider, status, body)
    with pytest.raises(DomainError) as err:
        sms.send_otp("9876543210", "123456", "registration")
    assert err.value.status_code == 502 and err.value.code == "SMS_FAILED"


def test_registration_sends_the_otp(client, gateway):
    calls = gateway("msg91")
    r = client.post(f"{U}/generate-otp", json={"phone": "9876500011", "password": "Secret@123"})
    assert r.status_code == 200, r.text
    assert calls and calls[0].url.params["otp"] == r.json()["otp"]


def test_gateway_down_tells_the_user_to_retry(client, gateway):
    gateway("twilio", 503)
    r = client.post(f"{U}/generate-otp", json={"phone": "9876500012", "password": "Secret@123"})
    assert r.status_code == 502 and r.json()["code"] == "SMS_FAILED"
