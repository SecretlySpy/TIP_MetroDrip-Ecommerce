"""Fulfillment v1 round trip: the real Django provider against the real service."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import override_settings

from apps.shipping.models import ShipmentStatus
from apps.shipping.providers.http import HttpShippingProvider
from services.fulfillment.main import app

SERVICE_SETTINGS = {
    "SHIPPING_SERVICE_URL": "http://fulfillment.test",
    "SHIPPING_SERVICE_TOKEN": "ship-secret",
}


def _pending_shipment():
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
    return shipment


@override_settings(**SERVICE_SETTINGS)
def test_booking_round_trip_applies_the_services_waybill(bridge, monkeypatch):
    """A real booking crosses the seam and lands on the Django row.

    This is the assertion the old split tests could not make: the field the
    service returns is the field the provider reads.
    """
    monkeypatch.setenv("SHIPPING_SERVICE_TOKEN", "ship-secret")
    recorded = bridge(app)
    shipment = _pending_shipment()

    assert HttpShippingProvider().book_shipment(shipment) is True

    assert shipment.waybill_no.startswith("JNT")
    assert shipment.tracking_url.endswith(shipment.waybill_no)
    assert shipment.status == ShipmentStatus.BOOKED
    assert shipment.booked_at is not None
    shipment.save.assert_called_once()

    assert len(recorded) == 1
    assert recorded[0]["path"] == "/v1/shipments/book"
    assert recorded[0]["json"]["order_no"] == "MD-2026-00042"
    assert recorded[0]["headers"]["Authorization"] == "Bearer ship-secret"


@override_settings(**SERVICE_SETTINGS)
def test_booking_is_refused_when_the_service_token_does_not_match(bridge, monkeypatch):
    """A token mismatch must fail the booking, not silently pass unauthenticated."""
    monkeypatch.setenv("SHIPPING_SERVICE_TOKEN", "a-different-secret")
    bridge(app)

    assert HttpShippingProvider().book_shipment(_pending_shipment()) is False


@override_settings(**SERVICE_SETTINGS)
def test_booking_is_refused_when_the_service_has_no_token(bridge, monkeypatch):
    """An unconfigured sidecar refuses rather than accepting anonymously."""
    monkeypatch.delenv("SHIPPING_SERVICE_TOKEN", raising=False)
    bridge(app)

    assert HttpShippingProvider().book_shipment(_pending_shipment()) is False


@override_settings(SHIPPING_SERVICE_URL="http://fulfillment.test", SHIPPING_SERVICE_TOKEN="")
def test_provider_refuses_to_call_without_its_own_token(bridge, monkeypatch):
    """Django must not send an unauthenticated request in the first place.

    Both ends used to fail open — the adapter omitted the header when its token
    was empty and the service skipped its check when its own was. Each half is
    now closed independently, so neither default can resurrect the other.
    """
    monkeypatch.setenv("SHIPPING_SERVICE_TOKEN", "ship-secret")
    recorded = bridge(app)

    assert HttpShippingProvider().book_shipment(_pending_shipment()) is False
    assert recorded == [], "no request should leave Django without a token"


@override_settings(**SERVICE_SETTINGS)
def test_non_pending_shipments_are_never_rebooked(bridge, monkeypatch):
    monkeypatch.setenv("SHIPPING_SERVICE_TOKEN", "ship-secret")
    recorded = bridge(app)
    shipment = _pending_shipment()
    shipment.status = ShipmentStatus.BOOKED

    assert HttpShippingProvider().book_shipment(shipment) is False
    assert recorded == []
