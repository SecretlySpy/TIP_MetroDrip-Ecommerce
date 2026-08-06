"""The last gate before cutover: no-oversell when reserves cross a network.

ADR-P3-023 recorded this as the one property still unproven. Everything else
about the service provider is verified — 30 parity assertions, single-threaded
round trips, idempotency serial and concurrent — but every one of those either
runs in-process or runs one caller at a time. None of them answers the question
the strangler step actually turns on: *when twenty buyers reserve the same SKU
simultaneously over HTTP, does exactly the available quantity get sold?*

The mechanism is the same InnoDB row lock either way, so it ought to hold. But
"ought to hold" is precisely the reasoning ADR-P3-002 reverted over, when an
extraction broke Hard Invariants 1 and 4 and nothing compared the two paths.

These run against a **real uvicorn process** on real sockets. The previous
attempt used Starlette's in-process `TestClient`, which cannot work here: it
drives each request on its own event loop while the ledger's `AsyncEngine`
cannot be shared across loops, so the buyers deadlocked in the harness. One
process, one loop, one engine, real HTTP — the same shape as production.
"""

from __future__ import annotations

import json
from queue import Queue
from threading import Barrier, Thread

import pytest
from django.db import connections
from django.test import Client, override_settings
from django.urls import reverse

from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import Reservation, ReservationStatus, StockMovement, StockRecord
from apps.inventory.services import reserve_lines
from apps.orders.models import Order, StockHold
from apps.shipping.models import ShippingZone

BUYERS = 20
UNITS = 10


def _stocked(*, sku, qty_on_hand):
    category, _ = Category.objects.get_or_create(name="Net", slug="net")
    product, _ = Product.objects.get_or_create(
        name="Net Product",
        slug="net-product",
        defaults={"category": category, "base_price": 100_00},
    )
    variant = ProductVariant.objects.create(
        product=product, sku=sku, size=Size.M, color=sku, fit=Fit.REGULAR
    )
    StockRecord.objects.create(variant=variant, qty_on_hand=qty_on_hand, qty_reserved=0)
    return variant


def _zone():
    zone, _ = ShippingZone.objects.get_or_create(
        name="NCR", defaults={"fee": 50_00, "is_active": True}
    )
    return zone


def _race(worker, count, *, timeout=180):
    """Run `worker(index)` on `count` threads released together by a barrier."""
    start_together = Barrier(count)
    outcomes = Queue()

    def run(index):
        # Django connections are thread-local. A fresh one per thread is what
        # makes the contention real rather than an artefact of sharing a session.
        connections.close_all()
        try:
            start_together.wait(timeout=30)
            outcomes.put(worker(index))
        except BaseException as error:  # noqa: BLE001 — re-raised in the main thread
            outcomes.put(error)
        finally:
            connections.close_all()

    threads = [Thread(target=run, args=(i,), name=f"net-buyer-{i}") for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=timeout)

    assert all(not thread.is_alive() for thread in threads), "a buyer thread hung"
    results = [outcomes.get_nowait() for _ in threads]
    errors = [item for item in results if isinstance(item, BaseException)]
    assert errors == [], f"unexpected worker failures: {errors[:3]}"
    return results


@pytest.mark.django_db(transaction=True)
def test_concurrent_reserves_over_the_network_never_oversell(ledger_process):
    """20 simultaneous reserves for 10 units: exactly 10 succeed.

    The narrowest form of the question — no checkout, no order, just the ledger
    under concurrent load across a socket.
    """
    variant = _stocked(sku="NET-RESERVE", qty_on_hand=UNITS)

    def reserve(index):
        from apps.inventory.services import InsufficientStock

        try:
            reserve_lines(
                checkout_id=f"net-reserve-{index:04d}",
                lines=[{"variant_id": variant.pk, "qty": 1}],
            )
            return "reserved"
        except InsufficientStock:
            return "insufficient"

    results = _race(reserve, BUYERS)

    assert results.count("reserved") == UNITS, f"expected {UNITS} winners, got {results}"
    assert results.count("insufficient") == BUYERS - UNITS

    record = StockRecord.objects.get(variant=variant)
    assert record.qty_on_hand == UNITS, "a hold must not consume physical stock"
    assert record.qty_reserved == UNITS
    assert record.available == 0, "Hard Invariant 1 across a network boundary"
    assert (
        Reservation.objects.filter(variant=variant, status=ReservationStatus.ACTIVE).count()
        == UNITS
    )


@pytest.mark.django_db(transaction=True)
@override_settings(PAYMENT_PROVIDER="simulated")
def test_m2_gate_through_web_checkout_with_a_remote_ledger(ledger_process):
    """The M2 release gate end to end: real checkout, real ledger, real sockets.

    This is ADR-P3-007 unlock item 4 in the form that actually matters. Stock is
    reserved over HTTP *before* the order row exists (ADR-P3-022), so nothing
    serialises the callers — the ledger's own row lock is the only thing
    standing between 20 buyers and an oversell.
    """
    variant = _stocked(sku="NET-CHECKOUT", qty_on_hand=UNITS)
    payload = {
        "customer_name": "Juan dela Cruz",
        "email": "juan@example.com",
        "phone": "09171234567",
        "address_line1": "123 Kalayaan Ave",
        "city": "Quezon City",
        "zone_id": _zone().pk,
        "items": [{"variant_id": variant.pk, "qty": 1}],
    }

    def buy(_index):
        return (
            Client()
            .post(
                reverse("storefront:checkout"),
                json.dumps(payload),
                content_type="application/json",
            )
            .status_code
        )

    results = _race(buy, BUYERS)

    assert results.count(200) == UNITS, f"expected exactly {UNITS} sales, got {results}"
    assert results.count(409) == BUYERS - UNITS, "the rest must be told they sold out"

    record = StockRecord.objects.get(variant=variant)
    assert (record.qty_on_hand, record.qty_reserved, record.available) == (UNITS, UNITS, 0)

    # Each winner leaves exactly one order and one hold receipt, and the losers
    # leave nothing at all — reserve-before-order writes no row when it fails.
    assert Order.objects.count() == UNITS
    assert StockHold.objects.count() == UNITS
    assert len({hold.checkout_id for hold in StockHold.objects.all()}) == UNITS
    assert not StockMovement.objects.exists(), "holds are not sales"


@pytest.mark.django_db(transaction=True)
def test_concurrent_retries_of_one_checkout_id_hold_once_over_the_network(ledger_process):
    """The idempotency protocol under real concurrent HTTP.

    A client that never learned the outcome of a request can have several
    retries in flight at once. In-process, G5 already showed a read-then-write
    guard is not a guard; this proves the ledger's own claim-row protocol holds
    when the racing callers are separate sockets rather than separate threads.
    """
    variant = _stocked(sku="NET-IDEM", qty_on_hand=UNITS)
    checkout_id = "net-shared-checkout-id"

    def reserve(_index):
        try:
            reserve_lines(checkout_id=checkout_id, lines=[{"variant_id": variant.pk, "qty": 3}])
            return "ok"
        except Exception as error:  # noqa: BLE001 — contention is a valid outcome
            return type(error).__name__

    _race(reserve, 5)

    record = StockRecord.objects.get(variant=variant)
    assert record.qty_reserved == 3, "one checkout_id must hold its units exactly once"
    assert Reservation.objects.filter(checkout_id=checkout_id).count() == 1


@pytest.mark.django_db(transaction=True)
def test_an_unreachable_ledger_fails_checkout_closed(ledger_process, settings):
    """Negative control: the gates above must be capable of failing.

    A suite that only ever asserts success cannot distinguish "the remote path
    works" from "the remote path was never taken". Pointing the provider at a
    dead port proves the traffic is real — and simultaneously pins the
    fail-closed behaviour, since a stock service that cannot be reached must
    stop the sale rather than let it through unreserved.
    """
    from apps.inventory.services import ReservationUnavailable

    variant = _stocked(sku="NET-DEAD", qty_on_hand=UNITS)

    # A port nothing is listening on. Connection is refused before any request
    # is sent, so this is the definite-no branch, not the uncertain one.
    settings.INVENTORY_SERVICE_URL = "http://127.0.0.1:1"

    with pytest.raises(ReservationUnavailable):
        reserve_lines(checkout_id="net-dead-0001", lines=[{"variant_id": variant.pk, "qty": 1}])

    record = StockRecord.objects.get(variant=variant)
    assert record.qty_reserved == 0, "an unreachable ledger must hold nothing"
    assert not Reservation.objects.filter(checkout_id="net-dead-0001").exists()
    assert Order.objects.count() == 0
