"""The stock commit inside the payment transaction runs on a bounded budget.

ADR-P3-025 recorded the hazard: under `INVENTORY_PROVIDER=service`,
`consume_order_holds` makes an HTTP call while the payment transaction holds a
row lock on `Payment`. It was using `_WRITE_POLICY` — three attempts at
1s connect + 5s read — so a sick-but-reachable ledger could keep that lock for
~18 seconds per paid order, which is how a slow sidecar becomes a stalled
database (ADR-P3-018 names the shape; the commit path was still doing it).

ADR-P3-028 cuts the in-transaction call to a single 1s+2s attempt. What makes
that safe rather than a trade is the outbox: `consume_order_holds` commits a
`stock.commit` row in the same transaction *before* it calls, so a timeout
loses only immediacy, never the commit. The drainer then retries outside any
transaction, with the full budget.

These tests assert the budget, not the mechanism — they measure wall clock
against a deliberately unresponsive ledger rather than reading the policy back.
"""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from django.test import override_settings

from apps.inventory.providers.service import ServiceInventoryProvider
from apps.inventory.services import ReservationUnavailable

# Comfortably above the 1s connect + 2s read in-transaction budget and well
# below the ~18s the full write policy would spend.
IN_TXN_CEILING_SECONDS = 6.0

# The stall must outlast the read timeout so the client gives up first; short
# enough that a hung test still finishes.
_STALL_SECONDS = 20


class _StallingLedger(BaseHTTPRequestHandler):
    """Accepts the connection, reads the body, then never answers.

    This is the failure mode that matters. A refused connection fails in
    milliseconds and would prove nothing about the read timeout; a ledger that
    accepts and then stalls is what actually holds the lock open.
    """

    def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler's required name
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        time.sleep(_STALL_SECONDS)

    def log_message(self, *args):
        """Silence the default stderr access log."""


@pytest.fixture()
def stalling_ledger():
    """A real socket that accepts requests and never replies."""
    server = HTTPServer(("127.0.0.1", 0), _StallingLedger)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _elapsed_commit(*, inside_transaction):
    """Wall-clock seconds for one commit_holds against the stalling ledger."""
    provider = ServiceInventoryProvider()
    started = time.monotonic()
    with pytest.raises(ReservationUnavailable):
        provider.commit_holds(
            checkout_id="budget-probe",
            order_no="MD-2026-00001",
            inside_transaction=inside_transaction,
        )
    return time.monotonic() - started


@pytest.mark.slow
def test_in_transaction_commit_gives_up_within_its_budget(stalling_ledger):
    """A stalled ledger must not hold the payment transaction open indefinitely."""
    from apps.core.http import BREAKER

    BREAKER.reset()
    with override_settings(
        INVENTORY_SERVICE_URL=stalling_ledger,
        INVENTORY_SERVICE_TOKEN="test-token",
    ):
        elapsed = _elapsed_commit(inside_transaction=True)

    assert elapsed < IN_TXN_CEILING_SECONDS, (
        f"in-transaction commit took {elapsed:.1f}s against a stalled ledger; "
        f"the payment row lock must be released within {IN_TXN_CEILING_SECONDS}s"
    )


@pytest.mark.slow
def test_the_outbox_retry_path_keeps_the_longer_budget(stalling_ledger):
    """The drainer holds no transaction, so it is allowed to try harder.

    Pins the asymmetry rather than just the fast path: if a later change gave
    every caller the tight budget, the outbox would quietly lose its retries and
    this test is what notices.
    """
    from apps.core.http import BREAKER

    BREAKER.reset()
    with override_settings(
        INVENTORY_SERVICE_URL=stalling_ledger,
        INVENTORY_SERVICE_TOKEN="test-token",
    ):
        elapsed = _elapsed_commit(inside_transaction=False)

    assert elapsed > IN_TXN_CEILING_SECONDS, (
        f"the retry path gave up after {elapsed:.1f}s — it should outlast the "
        "in-transaction budget, otherwise the outbox has silently lost its retries"
    )


def test_an_unreachable_ledger_still_fails_closed(stalling_ledger):
    """Bounding the budget must not turn a failed commit into a silent success."""
    from apps.core.http import BREAKER

    BREAKER.reset()
    # Bind a port and close it, so connections are refused rather than stalled.
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
    probe.close()

    provider = ServiceInventoryProvider()
    with override_settings(
        INVENTORY_SERVICE_URL=f"http://127.0.0.1:{dead_port}",
        INVENTORY_SERVICE_TOKEN="test-token",
    ):
        with pytest.raises(ReservationUnavailable):
            provider.commit_holds(checkout_id="dead-probe", inside_transaction=True)
