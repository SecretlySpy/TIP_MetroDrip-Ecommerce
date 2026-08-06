"""Phase 3 — fulfillment sidecar behaviour (booking only; default stays in-process).

The Django provider is exercised against this same app for real in
`tests/contract/test_fulfillment_v1.py`; this file covers the service alone.
"""

from __future__ import annotations


def test_fulfillment_service_is_not_ready_and_refuses_booking_without_a_token(monkeypatch):
    """A sidecar that cannot authenticate must neither serve nor report ready."""
    from fastapi.testclient import TestClient

    from services.fulfillment.main import app

    monkeypatch.delenv("SHIPPING_SERVICE_TOKEN", raising=False)
    client = TestClient(app)

    assert client.get("/healthz/live").json() == {"status": "ok"}

    ready = client.get("/healthz/ready")
    assert ready.status_code == 503
    assert ready.json() == {"status": "unavailable", "auth": "unconfigured"}

    refused = client.post("/v1/shipments/book", json={"order_no": "MD-1", "courier": "jnt"})
    assert refused.status_code == 503
    assert refused.json()["detail"]["error"]["code"] == "auth_not_configured"


def test_fulfillment_service_health_and_book(monkeypatch):
    from fastapi.testclient import TestClient

    from services.fulfillment.main import app

    monkeypatch.setenv("SHIPPING_SERVICE_TOKEN", "ship-secret")
    client = TestClient(app)
    assert client.get("/healthz/live").json() == {"status": "ok"}
    assert client.get("/healthz/ready").status_code == 200

    assert (
        client.post("/v1/shipments/book", json={"order_no": "MD-1", "courier": "jnt"}).status_code
        == 401
    )

    booked = client.post(
        "/v1/shipments/book",
        json={"order_no": "MD-1", "courier": "jnt", "correlation_id": "c1"},
        headers={"Authorization": "Bearer ship-secret"},
    )
    assert booked.status_code == 200
    body = booked.json()
    assert body["waybill_no"].startswith("JNT")
    assert body["status"] == "booked"
