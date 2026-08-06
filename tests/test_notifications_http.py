"""Phase 3 — notifications sidecar behaviour (delivery only; default stays local).

The Django provider is exercised against this same app for real in
`tests/contract/test_notifications_v1.py`; this file covers the service alone.
"""

from __future__ import annotations


def test_notifications_service_liveness_never_depends_on_configuration(monkeypatch):
    """Liveness answers even unconfigured — it only reports that a process runs."""
    from fastapi.testclient import TestClient

    from services.notifications.main import app

    monkeypatch.delenv("NOTIFICATION_SERVICE_TOKEN", raising=False)
    assert TestClient(app).get("/healthz/live").json() == {"status": "ok"}


def test_notifications_service_is_not_ready_without_a_token(monkeypatch):
    """A sidecar that cannot authenticate must never enter rotation."""
    from fastapi.testclient import TestClient

    from services.notifications.main import app

    monkeypatch.delenv("NOTIFICATION_SERVICE_TOKEN", raising=False)
    response = TestClient(app).get("/healthz/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "auth": "unconfigured"}


def test_notifications_service_refuses_delivery_without_a_token(monkeypatch):
    """Unconfigured must mean "refuse everything", not "accept everything"."""
    from fastapi.testclient import TestClient

    from services.notifications.main import app

    monkeypatch.delenv("NOTIFICATION_SERVICE_TOKEN", raising=False)
    response = TestClient(app).post("/v1/sms", json={"phone": "+63917", "message": "x"})

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "auth_not_configured"


def test_notifications_service_email_simulated_without_smtp(monkeypatch):
    from fastapi.testclient import TestClient

    from services.notifications.main import app

    monkeypatch.setenv("NOTIFICATION_SERVICE_TOKEN", "locked")
    response = TestClient(app).post(
        "/v1/email",
        json={
            "to": ["a@example.com"],
            "subject": "hi",
            "body": "body",
            "correlation_id": "cid-1",
        },
        headers={"Authorization": "Bearer locked"},
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "simulated"


def test_notifications_service_auth_when_token_set(monkeypatch):
    from fastapi.testclient import TestClient

    from services.notifications.main import app

    monkeypatch.setenv("NOTIFICATION_SERVICE_TOKEN", "locked")
    client = TestClient(app)

    assert client.get("/healthz/ready").status_code == 200

    denied = client.post("/v1/sms", json={"phone": "+63917", "message": "x"})
    assert denied.status_code == 401
    assert denied.json()["detail"]["error"]["code"] == "unauthorized"

    wrong = client.post(
        "/v1/sms",
        json={"phone": "+63917", "message": "x"},
        headers={"Authorization": "Bearer not-the-token"},
    )
    assert wrong.status_code == 401

    ok = client.post(
        "/v1/sms",
        json={"phone": "+63917", "message": "x"},
        headers={"Authorization": "Bearer locked"},
    )
    assert ok.status_code == 200
