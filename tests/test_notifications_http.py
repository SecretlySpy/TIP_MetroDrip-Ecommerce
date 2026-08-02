"""Phase 3 — notifications HTTP strangler (delivery only; default stays local)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import override_settings

from apps.notifications.providers.http import HttpNotificationProvider


@override_settings(
    NOTIFICATION_SERVICE_URL="http://notifications.test",
    NOTIFICATION_SERVICE_TOKEN="secret-token",
)
def test_http_provider_posts_email_dto():
    provider = HttpNotificationProvider()
    order = MagicMock()
    order.order_no = "MD-2026-00001"
    order.total = 19900
    order.shipping_address = {"email": "buyer@example.com"}
    order.customer = None

    with patch("apps.notifications.providers.http.requests.post") as post:
        post.return_value.status_code = 200
        assert provider.send_order_confirmation(order, "https://example.test/o/1") is True
        assert post.call_count == 1
        args, kwargs = post.call_args
        assert args[0] == "http://notifications.test/v1/email"
        assert kwargs["json"]["to"] == ["buyer@example.com"]
        assert "MD-2026-00001" in kwargs["json"]["subject"]
        assert kwargs["headers"]["Authorization"] == "Bearer secret-token"


@override_settings(NOTIFICATION_SERVICE_URL="http://notifications.test")
def test_http_provider_swallows_transport_errors():
    provider = HttpNotificationProvider()
    with patch(
        "apps.notifications.providers.http.requests.post",
        side_effect=ConnectionError("down"),
    ):
        assert provider.send_sms("+639171234567", "hello") is False


def test_notifications_service_health_endpoints():
    from fastapi.testclient import TestClient

    from services.notifications.main import app

    client = TestClient(app)
    assert client.get("/healthz/live").json() == {"status": "ok"}
    assert client.get("/healthz/ready").json() == {"status": "ok"}


def test_notifications_service_email_simulated_without_smtp():
    from fastapi.testclient import TestClient

    from services.notifications.main import app

    client = TestClient(app)
    response = client.post(
        "/v1/email",
        json={
            "to": ["a@example.com"],
            "subject": "hi",
            "body": "body",
            "correlation_id": "cid-1",
        },
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "simulated"


def test_notifications_service_auth_when_token_set(monkeypatch):
    from fastapi.testclient import TestClient

    import services.notifications.main as notif_main

    monkeypatch.setattr(notif_main, "SERVICE_TOKEN", "locked")
    client = TestClient(notif_main.app)
    denied = client.post(
        "/v1/sms",
        json={"phone": "+63917", "message": "x"},
    )
    assert denied.status_code == 401
    ok = client.post(
        "/v1/sms",
        json={"phone": "+63917", "message": "x"},
        headers={"Authorization": "Bearer locked"},
    )
    assert ok.status_code == 200
