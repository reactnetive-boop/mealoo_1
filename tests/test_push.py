"""PR-03: notifications reach phones as pushes, only after the action commits."""

import json

import httpx
import pytest

from app.core import push
from app.domain import notify
from app.models.device_push_token_model import DevicePushToken
from tests import factories as f

TOKEN = "ExponentPushToken[abcdefghijklmnop]"


@pytest.fixture
def expo(monkeypatch):
    sent = []
    tickets = {"value": None}

    def handler(request: httpx.Request):
        batch = json.loads(request.content)
        sent.extend(batch)
        data = tickets["value"] or [{"status": "ok", "id": "x"} for _ in batch]
        return httpx.Response(200, json={"data": data})

    monkeypatch.setattr(push, "PUSH_PROVIDER", "expo")
    monkeypatch.setattr(push, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(push, "_sync", True)
    return sent, tickets


def test_registered_device_gets_the_push_after_commit(client, db, expo):
    sent, _ = expo
    user, _, hdr = f.customer(db)
    assert client.post("/api/v1/user/push-token", headers=hdr, json={"token": TOKEN, "platform": "android"}).status_code == 200

    notify.customer(db, user.user_id, "order_status", "Out for delivery", "Your lunch is on the way", {"order_id": "o1"})
    assert sent == []          # nothing before the commit
    db.commit()
    assert sent[0]["to"] == TOKEN and sent[0]["title"] == "Out for delivery"
    assert sent[0]["data"] == {"order_id": "o1", "type": "order_status"}


def test_rolled_back_action_sends_nothing(db, client, expo):
    sent, _ = expo
    user, _, hdr = f.customer(db)
    client.post("/api/v1/user/push-token", headers=hdr, json={"token": TOKEN})
    notify.customer(db, user.user_id, "x", "Never", "rolled back")
    db.rollback()
    db.commit()
    assert sent == []


def test_dead_tokens_are_pruned(client, db, expo):
    sent, tickets = expo
    kitchen, hdr = f.provider(db)
    client.post("/api/v1/provider/push-token", headers=hdr, json={"token": TOKEN})
    tickets["value"] = [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]
    notify.kitchen(db, kitchen.provider_id, "new_order", "New order", "Thali x 2")
    db.commit()
    db.expire_all()
    assert db.query(DevicePushToken).count() == 0


def test_a_phone_belongs_to_whoever_logged_in_last(client, db):
    _, _, first = f.customer(db)
    second_user, _, second = f.customer(db)
    client.post("/api/v1/user/push-token", headers=first, json={"token": TOKEN})
    client.post("/api/v1/user/push-token", headers=second, json={"token": TOKEN})
    row = db.query(DevicePushToken).one()
    assert row.owner_id == second_user.user_id
    # only the owner can switch it off
    assert client.request("DELETE", "/api/v1/user/push-token", headers=first, json={"token": TOKEN}).status_code == 200
    assert db.query(DevicePushToken).count() == 1
    client.request("DELETE", "/api/v1/user/push-token", headers=second, json={"token": TOKEN})
    db.expire_all()
    assert db.query(DevicePushToken).count() == 0


def test_partner_registration_and_token_format(client, db):
    _, hdr = f.delivery_boy(db)
    assert client.post("/api/v1/delivery/push-token", headers=hdr, json={"token": "not-a-token"}).status_code == 422
    assert client.post("/api/v1/delivery/push-token", headers=hdr, json={"token": TOKEN}).status_code == 200
