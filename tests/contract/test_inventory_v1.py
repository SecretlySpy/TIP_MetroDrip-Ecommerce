"""Inventory v1 surface: routing, auth, and the idempotency contract.

Scope note. These cover the parts reachable without a live ledger database:
route registration, the auth boundary, and the pure logic of the replay
protocol. Driving reserve/commit/release against real rows needs a database
that is **not** pytest-django's own test database — pointing the service there
is what made every previous service-provider test a false green (ADR-P3-012),
and standing up a proper second schema with its own lifecycle is the harness
work that gates the parity claim in ADR-P3-005.

So: what is asserted here is asserted honestly, and what is missing is missing
on purpose rather than by oversight.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from contracts.inventory_v1 import (
    ROUTE_ADJUSTMENTS,
    ROUTE_COMMIT,
    ROUTE_RELEASE,
    ROUTE_RESERVATIONS,
    ROUTE_STOCK_BATCH,
    ROUTE_SWEEP,
)
from services.inventory import idempotency
from services.inventory.main import app

MUTATING_ROUTES = [
    ROUTE_RESERVATIONS,
    ROUTE_COMMIT.format(checkout_id="abc123"),
    ROUTE_RELEASE.format(checkout_id="abc123"),
    ROUTE_ADJUSTMENTS,
    ROUTE_SWEEP,
]


def _registered_paths() -> set[str]:
    """Paths as the app actually serves them.

    Read from the OpenAPI schema rather than `app.routes`: this FastAPI version
    keeps an included router as a single wrapper entry instead of flattening
    its routes into the app, so walking `app.routes` silently sees none of them.
    """
    return set(app.openapi()["paths"])


def test_every_v1_route_is_registered():
    """Catches a contract constant drifting away from its decorator."""
    paths = _registered_paths()
    for expected in (
        ROUTE_STOCK_BATCH,
        ROUTE_RESERVATIONS,
        ROUTE_ADJUSTMENTS,
        ROUTE_SWEEP,
    ):
        assert expected in paths, f"{expected} is not routed"

    # Path-parameter routes keep their template form in the route table.
    assert ROUTE_COMMIT in paths
    assert ROUTE_RELEASE in paths


@pytest.mark.parametrize("route", MUTATING_ROUTES)
def test_mutating_routes_refuse_an_unconfigured_service(route, monkeypatch):
    """No stock mutation is reachable without a configured service token.

    `POST /reservations` in particular was previously published on 0.0.0.0 with
    no authentication of any kind.
    """
    monkeypatch.delenv("INVENTORY_SERVICE_TOKEN", raising=False)
    response = TestClient(app).post(route, json={})

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "auth_not_configured"


@pytest.mark.parametrize("route", MUTATING_ROUTES)
def test_mutating_routes_reject_a_wrong_token(route, monkeypatch):
    monkeypatch.setenv("INVENTORY_SERVICE_TOKEN", "the-real-token")
    response = TestClient(app).post(
        route, json={}, headers={"Authorization": "Bearer not-the-token"}
    )

    assert response.status_code == 401


def test_readiness_is_false_without_a_token(monkeypatch):
    monkeypatch.delenv("INVENTORY_SERVICE_TOKEN", raising=False)
    response = TestClient(app).get("/healthz/ready")

    assert response.status_code == 503
    assert response.json()["auth"] == "unconfigured"


# --- The replay protocol's pure logic ---------------------------------------


def test_key_hash_is_namespaced_by_route():
    """One checkout_id must be able to guard reserve *and* commit separately.

    Without namespacing, committing would replay the reserve's stored response
    and silently skip the sale.
    """
    assert idempotency.hash_key(ROUTE_RESERVATIONS, "abc") != idempotency.hash_key(
        ROUTE_COMMIT, "abc"
    )


def test_fingerprint_is_stable_across_key_order_but_not_values():
    """Retries reorder JSON keys; a genuinely different body must not match."""
    assert idempotency.fingerprint({"a": 1, "b": 2}) == idempotency.fingerprint({"b": 2, "a": 1})
    assert idempotency.fingerprint({"a": 1}) != idempotency.fingerprint({"a": 2})


def test_fingerprint_distinguishes_nested_quantity_changes():
    """The realistic reuse case: same checkout_id, edited cart."""
    one = {"checkout_id": "c1", "lines": [{"variant_id": 1, "qty": 2}]}
    two = {"checkout_id": "c1", "lines": [{"variant_id": 1, "qty": 3}]}

    assert idempotency.fingerprint(one) != idempotency.fingerprint(two)
