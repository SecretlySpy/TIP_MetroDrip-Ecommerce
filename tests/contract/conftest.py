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
