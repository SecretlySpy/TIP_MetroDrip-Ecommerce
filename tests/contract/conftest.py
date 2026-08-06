"""Drive a real Django provider against a real FastAPI app, in one process.

The tests these replace asserted each side of a seam against a stand-in: the
client's outgoing shape against a mocked `requests.post`, and the server's
shape against a `TestClient`. Nothing compared the two. Renaming a response
field on the server left the client test green while every real booking
returned False, because the two "contract tests" only ever proved each side
self-consistent.

Because every adapter now posts through `apps/core/http.py`, redirecting that
one egress point is enough to make the Django provider talk to the actual
FastAPI app — no sockets, no fixtures, no running container.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from apps.core import http as core_http


@pytest.fixture
def bridge(monkeypatch):
    """Return a factory: `bridge(app)` -> list of recorded outbound requests."""

    def _install(app):
        client = TestClient(app, raise_server_exceptions=False)
        recorded: list[dict] = []

        def _request(method, url, *, json=None, params=None, headers=None, timeout=None, **kwargs):
            path = urlsplit(url).path
            recorded.append(
                {"method": method, "path": path, "json": json, "headers": dict(headers or {})}
            )
            return client.request(method, path, json=json, params=params, headers=headers)

        # `requests.request` is what apps/core/http.py calls. The sidecars' own
        # outbound calls use `requests.post`, so they stay untouched.
        monkeypatch.setattr(core_http.requests, "request", _request)
        return recorded

    return _install


@pytest.fixture(autouse=True)
def _reset_breaker():
    """Keep one test's induced failures from opening another test's circuit."""
    core_http.BREAKER.reset()
    yield
    core_http.BREAKER.reset()


def _run(coroutine):
    """Run one coroutine to completion on a throwaway loop."""
    return asyncio.new_event_loop().run_until_complete(coroutine)


@pytest.fixture
def live_ledger(db):
    """Bind the stock ledger to Django's active test schema for one test.

    This is the harness ADR-P3-017 named as the gate on any parity claim, and
    it is deliberately not a return to the old arrangement. Previously
    `conftest.py` set `MYSQL_DATABASE_INVENTORY=test_metrodrip` at session
    scope with no test using it: accidental, unexercised, and it masked the
    dual-write bug because both sides silently addressed the same rows
    (ADR-P3-012).

    Pointing the service at Django's schema is nonetheless *correct* —
    ADR-P3-013 chose "shared schema, exclusive writer" so that rollback stays
    an environment variable. What was missing was making it deliberate and
    actually testing it.

    Callers must also use `transaction=True`: the service reads on its own
    SQLAlchemy connection and cannot see an uncommitted Django transaction, so
    without a real COMMIT every read returns empty and the test proves the
    opposite of what it claims.
    """
    from django.db import connection

    from services.inventory import database

    schema = connection.settings_dict["NAME"]
    _run(database.configure(database=schema, echo=False, pooled=False))
    try:
        yield schema
    finally:
        # Drop the pool before Django's teardown truncates these tables.
        _run(database.engine.dispose())


@pytest.fixture
def service_provider(settings, monkeypatch, live_ledger, bridge):
    """Route Django's inventory calls over HTTP into the in-process ledger.

    Combines the three things a real round trip needs: the provider selected, a
    reachable and authenticated service, and the egress point redirected at the
    actual FastAPI app rather than at a mock.
    """
    from services.inventory.main import app

    token = "ledger-test-token"
    monkeypatch.setenv("INVENTORY_SERVICE_TOKEN", token)
    settings.INVENTORY_PROVIDER = "service"
    settings.INVENTORY_SERVICE_URL = "http://inventory.test"
    settings.INVENTORY_SERVICE_TOKEN = token
    return bridge(app)
