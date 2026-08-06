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
import os
import socket
import sys
import threading
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from apps.core import http as core_http


@pytest.fixture
def bridge(monkeypatch):
    """Return a factory: `bridge(app)` -> list of recorded outbound requests."""

    def _install(app):
        recorded: list[dict] = []
        record_lock = threading.Lock()

        def _request(method, url, *, json=None, params=None, headers=None, timeout=None, **kwargs):
            path = urlsplit(url).path
            with record_lock:
                recorded.append(
                    {"method": method, "path": path, "json": json, "headers": dict(headers or {})}
                )
            # A TestClient per call, not one shared across the fixture.
            #
            # Starlette's TestClient drives the ASGI app through a blocking
            # portal, and a single instance is not safe to call from many
            # threads at once: the concurrency gates deadlocked on it. That was
            # invisible while checkout reserved stock *inside* a Django
            # transaction, because the row lock serialised the callers and only
            # one ever reached the client at a time. Reserving before the order
            # row (ADR-P3-022) removed that accidental serialisation and the
            # harness limit surfaced immediately.
            #
            # Constructing a client per call is cheap, and requests still
            # execute concurrently against MySQL — which is the property these
            # gates actually test. Serialising with a lock instead would have
            # made them prove nothing.
            client = TestClient(app, raise_server_exceptions=False)
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


def _free_port():
    """Ask the OS for an unused port instead of guessing one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def ledger_process(db, settings):
    """Run the stock ledger as a real uvicorn process on Django's test schema.

    ADR-P3-023 removed the in-process concurrency gate because it could not
    work: Starlette's `TestClient` drives each request on its own AnyIO portal
    and event loop, while the ledger's `AsyncEngine` cannot be shared across
    loops. Concurrent buyers deadlocked in the harness before reaching any
    behaviour under test.

    A real process removes the whole class of problem. One uvicorn, one event
    loop, one engine, and genuine sockets — which is also how it runs in
    production, so what the gate proves is what actually ships.

    `SKIP_CREATE_ALL` is set because Django owns this DDL (ADR-P3-013,
    shared schema / exclusive writer). The service maps the tables; it must
    never create them.
    """
    import subprocess
    import time

    import requests as real_requests
    from django.db import connection

    schema = connection.settings_dict["NAME"]
    database = settings.DATABASES["default"]
    port = _free_port()
    token = "ledger-process-token"

    environment = {
        **os.environ,
        "MYSQL_DATABASE_INVENTORY": schema,
        "MYSQL_USER": database["USER"],
        "MYSQL_PASSWORD": database["PASSWORD"],
        "MYSQL_HOST": database["HOST"] or "127.0.0.1",
        "MYSQL_PORT": str(database["PORT"] or "3306"),
        "INVENTORY_SERVICE_TOKEN": token,
        "SKIP_CREATE_ALL": "1",
        "INVENTORY_DISABLE_REDIS": "1",
    }

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "services.inventory.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    base_url = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # Readiness, not liveness: it also proves the token is configured and
        # the ledger can actually reach the schema. A gate that starts against
        # a half-configured service measures nothing.
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read().decode("utf-8", "replace")
                raise RuntimeError(f"ledger exited during startup:\n{output[-2000:]}")
            try:
                probe = real_requests.get(f"{base_url}/healthz/ready", headers=headers, timeout=1)
                if probe.status_code == 200:
                    break
            except real_requests.RequestException:
                time.sleep(0.2)
        else:
            process.kill()
            raise RuntimeError(f"ledger never became ready on {base_url}")

        settings.INVENTORY_PROVIDER = "service"
        settings.INVENTORY_SERVICE_URL = base_url
        settings.INVENTORY_SERVICE_TOKEN = token

        # Prove the wiring rather than assume it. If the provider silently
        # resolved back to `local`, every test using this fixture would pass
        # while measuring the in-process path — the exact false green that
        # ADR-P3-012 was written about, and it would be invisible because the
        # assertions are about stock counters, which `local` also satisfies.
        from apps.inventory.providers import get_inventory_provider
        from apps.inventory.providers.service import ServiceInventoryProvider

        resolved = get_inventory_provider()
        assert isinstance(resolved, ServiceInventoryProvider), (
            f"expected the HTTP provider, resolved {type(resolved).__name__} — "
            "this gate would otherwise silently test the in-process path"
        )

        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
