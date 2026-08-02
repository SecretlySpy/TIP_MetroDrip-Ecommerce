"""FR-13 — province/city → ShippingZone resolution (server-side)."""

from __future__ import annotations

import pytest

from apps.shipping.models import ShippingZone
from apps.shipping.zones import resolve_zone, resolve_zone_name


@pytest.fixture
def zones(db):
    return {
        "NCR": ShippingZone.objects.create(name="NCR", fee=9900),
        "Luzon": ShippingZone.objects.create(name="Luzon", fee=15900),
        "VisMin": ShippingZone.objects.create(name="VisMin", fee=19900),
    }


@pytest.mark.parametrize(
    ("province", "city", "expected"),
    [
        ("Cebu", "", "VisMin"),
        ("Central Visayas", "Cebu City", "VisMin"),
        ("Davao del Sur", "Davao City", "VisMin"),
        ("Metro Manila", "Makati", "NCR"),
        ("National Capital Region", "", "NCR"),
        ("Laguna", "Calamba", "Luzon"),
        ("Calabarzon", "", "Luzon"),
        ("Benguet", "Baguio", "Luzon"),
    ],
)
def test_resolve_zone_name_maps_ph_localities(province, city, expected):
    assert resolve_zone_name(province, city=city) == expected


def test_resolve_zone_returns_active_row(zones):
    zone = resolve_zone("Cebu", city="Cebu City")
    assert zone is not None
    assert zone.name == "VisMin"
    assert zone.fee == 19900


def test_resolve_zone_empty_input_is_none(zones):
    assert resolve_zone("") is None
    assert resolve_zone_name("") is None


def test_web_resolve_endpoint_cebu_selects_vismin(client, zones):
    response = client.get(
        "/api/shipping/resolve-zone/",
        {"province": "Cebu", "city": "Cebu City"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["zone_id"] == zones["VisMin"].pk
    assert body["zone_name"] == "VisMin"
    assert body["fee"] == 19900
    assert body["fee_display"]
    assert response["X-Correlation-ID"]


def test_mobile_resolve_endpoint_cebu(client, zones):
    response = client.get(
        "/api/mobile/v1/shipping/zones/resolve/",
        {"province": "Cebu"},
        HTTP_X_CLIENT_VERSION="1.0.0-test",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["zone"]["name"] == "VisMin"
    assert body["zone"]["fee"] == 19900


def test_mobile_resolve_unknown_returns_null_zone(client, zones):
    response = client.get(
        "/api/mobile/v1/shipping/zones/resolve/",
        {"province": ""},
        HTTP_X_CLIENT_VERSION="1.0.0-test",
    )
    assert response.status_code == 200
    assert response.json() == {"zone": None}
