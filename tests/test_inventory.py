"""Concurrency release contracts for MetroDrip inventory reservations."""

from queue import Queue
from threading import Barrier, Thread

import pytest
from django.db import connections

from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import StockRecord


@pytest.mark.xfail(
    strict=True,
    raises=ImportError,
    reason="Epic B-1 must implement reserve_stock and InsufficientStock before this gate runs.",
)
@pytest.mark.django_db(transaction=True)
def test_two_buyers_competing_for_one_unit_produce_exactly_one_success():
    """Two real MySQL connections may reserve one unit only once, with no oversell."""
    # Keep imports inside the test so the intentionally missing B-1 API becomes the expected fail.
    from apps.inventory.services import InsufficientStock, reserve_stock

    # Committed setup is visible to the independent database connections used by both threads.
    category = Category.objects.create(name="Race Test", slug="race-test")
    product = Product.objects.create(
        name="Race Test Product",
        slug="race-test-product",
        category=category,
        base_price=100_00,
    )
    variant = ProductVariant.objects.create(
        product=product,
        sku="RACE-ONE-UNIT",
        size=Size.M,
        color="Black",
        fit=Fit.REGULAR,
    )
    stock = StockRecord.objects.create(variant=variant, qty_on_hand=1, qty_reserved=0)

    # The barrier aligns both attempts closely enough to exercise InnoDB row locking.
    start_together = Barrier(2)
    # A thread-safe queue records both business outcomes and unexpected worker exceptions.
    outcomes = Queue()

    def buyer() -> None:
        """Run one reservation attempt on this thread's own Django/MySQL connection."""
        # Django connections are thread-local; closing first guarantees a fresh session here.
        connections.close_all()
        try:
            # Neither buyer calls the service until both worker threads are ready.
            start_together.wait(timeout=10)
            reserve_stock(variant_id=variant.pk, qty=1)
        except InsufficientStock:
            # Losing because stock is already reserved is the one expected business rejection.
            outcomes.put("insufficient")
        except BaseException as error:  # noqa: BLE001
            # Preserve worker failures for an assertion in the main pytest thread.
            outcomes.put(error)
        else:
            outcomes.put("reserved")
        finally:
            # Do not leak thread-owned connections into later tests.
            connections.close_all()

    buyers = [Thread(target=buyer, name=f"buyer-{number}") for number in (1, 2)]
    for thread in buyers:
        thread.start()
    for thread in buyers:
        thread.join(timeout=15)

    # A deadlock or unbounded lock wait is itself a failed concurrency contract.
    assert all(not thread.is_alive() for thread in buyers)

    results = [outcomes.get_nowait() for _ in buyers]
    unexpected_errors = [result for result in results if isinstance(result, BaseException)]
    assert unexpected_errors == []
    assert sorted(results) == ["insufficient", "reserved"]

    stock.refresh_from_db()
    assert stock.qty_on_hand == 1
    assert stock.qty_reserved == 1
    assert stock.available == 0
