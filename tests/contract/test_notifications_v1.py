"""Notifications v1 round trip: the real Django provider against the real service."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import override_settings

from apps.notifications.providers.http import HttpNotificationProvider
from services.notifications.main import app

SERVICE_SETTINGS = {
    "NOTIFICATION_SERVICE_URL": "http://notifications.test",
    "NOTIFICATION_SERVICE_TOKEN": "notify-secret",
}


def _order():
    order = MagicMock()
    order.order_no = "MD-2026-00001"
    order.total = 19900
    order.shipping_address = {"email": "buyer@example.com"}
    order.customer = None
    return order


@override_settings(**SERVICE_SETTINGS)
def test_order_confirmation_round_trip(bridge, monkeypatch):
    monkeypatch.setenv("NOTIFICATION_SERVICE_TOKEN", "notify-secret")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    recorded = bridge(app)

    assert (
        HttpNotificationProvider().send_order_confirmation(_order(), "https://example.test/o/1")
        is True
    )

    assert len(recorded) == 1
    sent = recorded[0]
    assert sent["path"] == "/v1/email"
    assert sent["json"]["to"] == ["buyer@example.com"]
    assert "MD-2026-00001" in sent["json"]["subject"]
    assert sent["headers"]["Authorization"] == "Bearer notify-secret"


@override_settings(**SERVICE_SETTINGS)
def test_sms_round_trip(bridge, monkeypatch):
    monkeypatch.setenv("NOTIFICATION_SERVICE_TOKEN", "notify-secret")
    monkeypatch.delenv("SEMAPHORE_API_KEY", raising=False)
    recorded = bridge(app)

    assert HttpNotificationProvider().send_sms("+639171234567", "hello") is True
    assert recorded[0]["path"] == "/v1/sms"
    assert recorded[0]["json"]["phone"] == "+639171234567"


@override_settings(**SERVICE_SETTINGS)
def test_delivery_failure_is_swallowed_not_raised(bridge, monkeypatch):
    """Enhancement-tier: a rejected delivery must never raise into the caller."""
    monkeypatch.setenv("NOTIFICATION_SERVICE_TOKEN", "a-different-secret")
    bridge(app)

    assert HttpNotificationProvider().send_sms("+639171234567", "hello") is False


@override_settings(
    NOTIFICATION_SERVICE_URL="http://notifications.test", NOTIFICATION_SERVICE_TOKEN=""
)
def test_provider_refuses_to_call_without_its_own_token(bridge, monkeypatch):
    monkeypatch.setenv("NOTIFICATION_SERVICE_TOKEN", "notify-secret")
    recorded = bridge(app)

    assert HttpNotificationProvider().send_sms("+639171234567", "hello") is False
    assert recorded == [], "no request should leave Django without a token"


@override_settings(NOTIFICATION_SERVICE_URL="", NOTIFICATION_SERVICE_TOKEN="notify-secret")
def test_unconfigured_service_url_degrades_quietly(bridge, monkeypatch):
    monkeypatch.setenv("NOTIFICATION_SERVICE_TOKEN", "notify-secret")
    recorded = bridge(app)

    assert HttpNotificationProvider().send_sms("+639171234567", "hello") is False
    assert recorded == []
