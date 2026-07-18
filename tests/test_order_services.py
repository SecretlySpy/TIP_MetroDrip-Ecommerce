"""Integration tests for order services that depend on real MySQL locking."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import IntegrityError, close_old_connections, connections, transaction

from apps.orders.models import MAX_ORDER_SEQUENCE, OrderNumberSequence
from apps.orders.services import InvalidOrderYear, OrderNumberExhausted, next_order_no


@pytest.mark.django_db(transaction=True)
def test_next_order_no_is_unique_during_first_sequence_row_race():
    """Two first orders in a year must receive distinct, consecutive numbers."""
    start_together = Barrier(2)

    def allocate_number():
        # Django connections are thread-local. Closing inherited/stale handles
        # ensures each worker owns the independent transaction needed by this test.
        close_old_connections()
        start_together.wait(timeout=5)
        try:
            return next_order_no(year=2099)
        finally:
            # A worker-created connection must be closed in that worker so it
            # cannot leak into another test or remain checked out from MySQL.
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        allocated = list(executor.map(lambda _worker: allocate_number(), range(2)))

    assert sorted(allocated) == ["MD-2099-00001", "MD-2099-00002"]
    assert OrderNumberSequence.objects.get(year=2099).last_value == 2


@pytest.mark.django_db
@pytest.mark.parametrize("invalid_year", [999, 10_000, "2026", True])
def test_next_order_no_rejects_non_four_digit_integer_years(invalid_year):
    """The YYYY segment must be an actual four-digit integer."""
    with pytest.raises(InvalidOrderYear):
        next_order_no(year=invalid_year)


@pytest.mark.django_db
def test_next_order_no_stops_when_five_digit_sequence_is_exhausted():
    """Allocation must never silently widen the locked NNNNN format."""
    sequence = OrderNumberSequence.objects.create(year=2098, last_value=MAX_ORDER_SEQUENCE)

    with pytest.raises(OrderNumberExhausted):
        next_order_no(year=sequence.year)

    sequence.refresh_from_db()
    assert sequence.last_value == MAX_ORDER_SEQUENCE


@pytest.mark.django_db
def test_order_number_sequence_database_constraints_match_public_format():
    """Direct ORM writes cannot persist an invalid year or six-digit counter."""
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderNumberSequence.objects.create(year=999, last_value=0)

    with pytest.raises(IntegrityError), transaction.atomic():
        OrderNumberSequence.objects.create(year=2097, last_value=MAX_ORDER_SEQUENCE + 1)
