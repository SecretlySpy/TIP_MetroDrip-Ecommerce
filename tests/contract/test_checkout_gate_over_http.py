"""G3 re-pointed at the ledger: the M2 gate with stock held over HTTP.

This is ADR-P3-007's unlock item 4 in its strongest form. The gates in
`tests/test_checkout_concurrency.py` prove the guarantee holds when the row
lock and the order row share a transaction. This one proves it still holds
when the lock lives behind a network call and the order row does not — which
is the whole question the strangler step turns on, and the one ADR-P3-002's
revert answered badly.

If no-oversell survives here, the lock never needed to share the order's
transaction; it only needed to be atomic per reserve.
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
from apps.inventory.models import Reservation, ReservationStatus, StockRecord
from apps.orders.models import Order, StockHold
from apps.shipping.models import ShippingZone

BUYERS = 20
UNITS = 10


@pytest.mark.django_db(transaction=True)
@override_settings(PAYMENT_PROVIDER="simulated")
def test_g3_over_http_sells_ten_units_to_twenty_buyers(service_provider):
    """20 concurrent web checkouts, stock reserved over HTTP, exactly 10 win."""
    category, _ = Category.objects.get_or_create(name="GateHTTP", slug="gate-http")
    product, _ = Product.objects.get_or_create(
        name="Gate HTTP Product",
        slug="gate-http-product",
        defaults={"category": category, "base_price": 100_00},
    )
    variant = ProductVariant.objects.create(
        product=product, sku="GATE-HTTP", size=Size.M, color="GATE-HTTP", fit=Fit.REGULAR
    )
    StockRecord.objects.create(variant=variant, qty_on_hand=UNITS, qty_reserved=0)
    zone, _ = ShippingZone.objects.get_or_create(
        name="NCR", defaults={"fee": 50_00, "is_active": True}
    )

    payload = {
        "customer_name": "Juan dela Cruz",
        "email": "juan@example.com",
        "phone": "09171234567",
        "address_line1": "123 Kalayaan Ave",
        "city": "Quezon City",
        "zone_id": zone.pk,
        "items": [{"variant_id": variant.pk, "qty": 1}],
    }

    start_together = Barrier(BUYERS)
    outcomes = Queue()

    def buy():
        connections.close_all()
        try:
            start_together.wait(timeout=20)
            outcomes.put(
                Client()
                .post(
                    reverse("storefront:checkout"),
                    json.dumps(payload),
                    content_type="application/json",
                )
                .status_code
            )
        except BaseException as error:  # noqa: BLE001 — surfaced below
            outcomes.put(error)
        finally:
            connections.close_all()

    threads = [Thread(target=buy, name=f"http-buyer-{index}") for index in range(BUYERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=180)

    assert all(not thread.is_alive() for thread in threads), "a buyer thread hung"
    results = [outcomes.get_nowait() for _ in threads]
    errors = [item for item in results if isinstance(item, BaseException)]
    assert errors == [], f"unexpected worker failures: {errors[:3]}"

    assert results.count(200) == UNITS, f"expected exactly {UNITS} sales, got {results}"

    record = StockRecord.objects.get(variant=variant)
    assert record.qty_on_hand == UNITS, "holds must not consume physical stock"
    assert record.qty_reserved == UNITS
    assert record.available == 0, "no oversell, with the lock behind a network call"

    assert (
        Reservation.objects.filter(variant=variant, status=ReservationStatus.ACTIVE).count()
        == UNITS
    )
    assert Order.objects.count() == UNITS
    assert StockHold.objects.count() == UNITS
