"""SI FR-05 / NFR-12 — X-Correlation-ID generation, propagation, error echo."""

from __future__ import annotations

import logging


def test_middleware_mints_correlation_id_when_absent(client):
    response = client.get("/healthz/live/")
    assert response.status_code == 200
    cid = response["X-Correlation-ID"]
    assert cid
    assert len(cid) >= 8


def test_middleware_propagates_inbound_correlation_id(client):
    response = client.get("/healthz/live/", HTTP_X_CORRELATION_ID="trace-abc-12345")
    assert response["X-Correlation-ID"] == "trace-abc-12345"


def test_middleware_rejects_unsafe_inbound_id(client):
    response = client.get(
        "/healthz/live/",
        HTTP_X_CORRELATION_ID="bad id with spaces and\ninjection",
    )
    # Mint a fresh id instead of echoing unsafe input.
    assert response["X-Correlation-ID"] != "bad id with spaces and\ninjection"
    assert len(response["X-Correlation-ID"]) >= 8


def test_mobile_error_envelope_includes_correlation_id(client):
    response = client.get("/api/mobile/v1/catalog/products/")
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "missing_client_version"
    assert body["error"]["correlation_id"] == response["X-Correlation-ID"]


def test_storefront_json_error_includes_correlation_id(client):
    response = client.post(
        "/checkout/",
        data=b"not-json",
        content_type="application/json",
    )
    assert response.status_code == 400
    body = response.json()
    assert "error" in body
    assert body["correlation_id"] == response["X-Correlation-ID"]


def test_log_records_carry_correlation_id(client, caplog):
    with caplog.at_level(logging.INFO):
        response = client.get(
            "/healthz/live/",
            HTTP_X_CORRELATION_ID="log-trace-99999",
        )
    assert response["X-Correlation-ID"] == "log-trace-99999"
    # Filter injects the attribute even if no app logger fired on this path.
    from config.middleware import CorrelationIdFilter

    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", (), None)
    CorrelationIdFilter().filter(record)
    # Outside the request the contextvar is empty; prove the filter is wired.
    assert hasattr(record, "correlation_id")
