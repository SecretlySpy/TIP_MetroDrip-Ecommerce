"""Phase 3 — fulfillment HTTP strangler (booking only; default stays in-process)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import override_settings

from apps.shipping.models import ShipmentStatus
from apps.shipping.providers.http import HttpShippingProvider


@override_settings(
    SHIPPING_SERVICE_URL="http://fulfillment.test",
    SHIPPING_SERVICE_TOKEN="ship-secret",
)
def test_http_provider_applies_waybill_on_success():
    order = MagicMock()
    order.order_no = "MD-2026-00042"
    order.shipping_address = {
        "name": "Ada",
        "address_line1": "1 Test St",
        "city": "Makati",
        "phone": "+63917",
    }
    shipment = MagicMock()
    shipment.status = ShipmentStatus.PENDING
    shipment.courier = "jnt"
    shipment.order = order

    with patch("apps.shipping.providers.http.requests.post") as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            "waybill_no": "JNT123",
            "tracking_url": "https://track.example/JNT123",
            "status": "booked",
        }
        assert HttpShippingProvider().book_shipment(shipment) is True

    assert shipment.waybill_no == "JNT123"
    assert shipment.tracking_url == "https://track.example/JNT123"
    assert shipment.status == ShipmentStatus.BOOKED
    assert shipment.booked_at is not None
    shipment.save.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == "http://fulfillment.test/v1/shipments/book"
    assert kwargs["headers"]["Authorization"] == "Bearer ship-secret"
    assert kwargs["json"]["order_no"] == "MD-2026-00042"


@override_settings(SHIPPING_SERVICE_URL="http://fulfillment.test")
def test_http_provider_swallows_errors_and_skips_non_pending():
    shipment = MagicMock()
    shipment.status = ShipmentStatus.BOOKED
    assert HttpShippingProvider().book_shipment(shipment) is False

    shipment.status = ShipmentStatus.PENDING
    shipment.order = MagicMock(order_no="X", shipping_address={})
    shipment.courier = "jnt"
    with patch(
        "apps.shipping.providers.http.requests.post",
        side_effect=ConnectionError("down"),
    ):
        assert HttpShippingProvider().book_shipment(shipment) is False


def test_fulfillment_service_health_and_book():
    from fastapi.testclient import TestClient

    from services.fulfillment.main import app

    client = TestClient(app)
    assert client.get("/healthz/live").json() == {"status": "ok"}
    assert client.get("/healthz/ready").json() == {"status": "ok"}
    booked = client.post(
        "/v1/shipments/book",
        json={"order_no": "MD-1", "courier": "jnt", "correlation_id": "c1"},
    )
    assert booked.status_code == 200
    body = booked.json()
    assert body["waybill_no"].startswith("JNT")
    assert body["status"] == "booked"
