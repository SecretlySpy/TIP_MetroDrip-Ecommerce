"""Concurrency gates G3–G5: the M2 guarantee through the real checkout paths.

ADR-P3-007's unlock item 4 asks for the M2 gate to be re-pointed at the reserve
endpoint with "both web and mobile checkout must pass". Neither existed. The
gates in `test_inventory.py` race `reserve_stock` in isolation, which proves
the row lock but says nothing about the surface customers actually use — order
numbering, the deadlock retry, payment-session creation, and hold bookkeeping
all sit between an HTTP request and that lock.

These run on real threads against real MySQL connections. An engine without
row locks would serialise them into meaninglessness, which is why `transaction
=True` and MySQL are both load-bearing here rather than incidental.
"""

import json
from queue import Queue
from threading import Barrier, Thread

import pytest
from django.db import connections
from django.test import Client, override_settings
from django.urls import reverse

from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import Reservation, ReservationStatus, StockRecord
from apps.inventory.services import reserve_lines
from apps.orders.models import Order, StockHold
from apps.shipping.models import ShippingZone

BUYERS = 20
UNITS = 10


def _variant(*, sku="GATE-SKU", qty_on_hand=UNITS):
    category, _ = Category.objects.get_or_create(name="Gate", slug="gate")
    product, _ = Product.objects.get_or_create(
        name="Gate Product",
        slug="gate-product",
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


def _race(worker, count):
    """Run `worker(index)` on `count` threads aligned by a barrier."""
    start_together = Barrier(count)
    outcomes = Queue()

    def run(index):
        # Django connections are thread-local; a fresh session per thread is
        # what makes the row lock real rather than an artefact of sharing one.
        connections.close_all()
        try:
            start_together.wait(timeout=20)
            outcomes.put(worker(index))
        except BaseException as error:  # noqa: BLE001 — surfaced in the main thread
            outcomes.put(error)
        finally:
            connections.close_all()

    threads = [Thread(target=run, args=(index,), name=f"buyer-{index}") for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    # A deadlock or an unbounded lock wait is itself a failed contract.
    assert all(not thread.is_alive() for thread in threads), "a buyer thread hung"

    results = [outcomes.get_nowait() for _ in threads]
    errors = [item for item in results if isinstance(item, BaseException)]
    assert errors == [], f"unexpected worker failures: {errors[:3]}"
    return results


def _assert_exactly_ten_sold(variant):
    record = StockRecord.objects.get(variant=variant)
    assert record.qty_on_hand == UNITS, "holds must not consume physical stock"
    assert record.qty_reserved == UNITS, "every unit held exactly once"
    assert record.available == 0, "no oversell (Hard Invariant 1)"
    assert (
        Reservation.objects.filter(variant=variant, status=ReservationStatus.ACTIVE).count()
        == UNITS
    )


@pytest.mark.django_db(transaction=True)
@override_settings(PAYMENT_PROVIDER="simulated")
def test_g3_web_checkout_sells_ten_units_to_twenty_buyers():
    """G3 — the M2 gate through the web checkout endpoint."""
    variant = _variant(sku="GATE-WEB")
    zone = _zone()
    payload = {
        "customer_name": "Juan dela Cruz",
        "email": "juan@example.com",
        "phone": "09171234567",
        "address_line1": "123 Kalayaan Ave",
        "city": "Quezon City",
        "zone_id": zone.pk,
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

    assert results.count(200) == UNITS, f"expected {UNITS} successful checkouts, got {results}"
    assert results.count(409) == BUYERS - UNITS, "the rest must be told they sold out"
    _assert_exactly_ten_sold(variant)

    # Every successful checkout leaves exactly one order and one hold receipt.
    assert Order.objects.count() == UNITS
    assert StockHold.objects.count() == UNITS
    assert len({hold.checkout_id for hold in StockHold.objects.all()}) == UNITS


@pytest.mark.django_db(transaction=True)
@override_settings(PAYMENT_PROVIDER="simulated")
def test_g4_mobile_checkout_sells_ten_units_to_twenty_buyers():
    """G4 — the same gate through the mobile API, which is a separate caller."""
    variant = _variant(sku="GATE-MOBILE")
    zone = _zone()
    # The mobile API takes the same flat intent shape as the web endpoint —
    # both are thin callers of the one checkout service (ADR-H-002).
    body = {
        "customer_name": "Juan dela Cruz",
        "email": "juan@example.com",
        "phone": "09171234567",
        "address_line1": "123 Kalayaan Ave",
        "city": "Quezon City",
        "zone_id": zone.pk,
        "items": [{"variant_id": variant.pk, "qty": 1}],
    }

    def buy(_index):
        return (
            Client()
            .post(
                reverse("mobile_api:checkout"),
                json.dumps(body),
                content_type="application/json",
                HTTP_X_CLIENT_VERSION="1.0.0",
            )
            .status_code
        )

    results = _race(buy, BUYERS)

    successes = results.count(200) + results.count(201)
    assert successes == UNITS, f"expected {UNITS} successful checkouts, got {results}"
    _assert_exactly_ten_sold(variant)
    assert Order.objects.count() == UNITS


@pytest.mark.django_db(transaction=True)
def test_g5_concurrent_reserves_sharing_a_checkout_id_hold_once():
    """G5 — the replay guard under genuine concurrency, not just in sequence.

    A client that retries a request it never got an answer to can have several
    attempts in flight at once. Serial idempotency is easy; this is the case
    that actually distinguishes a correct implementation.
    """
    variant = _variant(sku="GATE-IDEM", qty_on_hand=UNITS)
    checkout_id = "gate-shared-checkout-id"
    lines = [{"variant_id": variant.pk, "qty": 3}]

    def reserve(_index):
        try:
            reserve_lines(checkout_id=checkout_id, lines=lines)
            return "ok"
        except Exception as error:  # noqa: BLE001 — contention is an acceptable outcome
            return type(error).__name__

    _race(reserve, 5)

    record = StockRecord.objects.get(variant=variant)
    assert record.qty_reserved == 3, "one checkout_id must hold its units exactly once"
    assert Reservation.objects.filter(checkout_id=checkout_id).count() == 1
