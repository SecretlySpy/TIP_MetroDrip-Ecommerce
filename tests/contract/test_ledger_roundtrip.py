"""Real round trips: Django's service provider against the running ledger.

Every test here uses `transaction=True` on purpose. The ledger reads on its own
SQLAlchemy connection, so it cannot see an uncommitted Django transaction —
without a genuine COMMIT these would read empty and quietly assert the
opposite of what they claim. That is the same class of mistake as ADR-P3-012,
so it is stated rather than assumed.
"""

from __future__ import annotations

import pytest

from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import (
    MovementReason,
    Reservation,
    ReservationStatus,
    StockMovement,
    StockRecord,
)
from apps.inventory.services import (
    InsufficientStock,
    commit_holds,
    get_stock_records,
    release_holds,
    reserve_lines,
)


def _stocked_variant(*, sku, qty_on_hand=10):
    category, _ = Category.objects.get_or_create(name="Ledger", slug="ledger")
    product, _ = Product.objects.get_or_create(
        name="Ledger Product",
        slug="ledger-product",
        defaults={"category": category, "base_price": 100_00},
    )
    variant = ProductVariant.objects.create(
        product=product, sku=sku, size=Size.M, color=sku, fit=Fit.REGULAR
    )
    StockRecord.objects.create(variant=variant, qty_on_hand=qty_on_hand, qty_reserved=0)
    return variant


@pytest.mark.django_db(transaction=True)
def test_reserve_over_http_moves_the_real_counters(service_provider):
    """The reserve actually reached a database, not a mock."""
    variant = _stocked_variant(sku="RT-RESERVE", qty_on_hand=10)

    created = reserve_lines(
        checkout_id="rt-reserve-0001", lines=[{"variant_id": variant.pk, "qty": 3}]
    )

    assert len(created) == 1
    record = StockRecord.objects.get(variant=variant)
    assert record.qty_reserved == 3, "the service must have written Django-visible rows"
    assert record.available == 7

    held = Reservation.objects.get(checkout_id="rt-reserve-0001")
    assert held.qty == 3
    assert held.status == ReservationStatus.ACTIVE


@pytest.mark.django_db(transaction=True)
def test_reserve_over_http_refuses_to_oversell(service_provider):
    """Hard Invariant 1 across the wire, with the 409 mapped back to a domain error."""
    variant = _stocked_variant(sku="RT-OVERSELL", qty_on_hand=2)

    with pytest.raises(InsufficientStock):
        reserve_lines(checkout_id="rt-oversell-0001", lines=[{"variant_id": variant.pk, "qty": 5}])

    assert StockRecord.objects.get(variant=variant).qty_reserved == 0
    assert not Reservation.objects.filter(checkout_id="rt-oversell-0001").exists()


@pytest.mark.django_db(transaction=True)
def test_reserve_is_all_or_nothing_across_the_wire(service_provider):
    plenty = _stocked_variant(sku="RT-PLENTY", qty_on_hand=10)
    scarce = _stocked_variant(sku="RT-SCARCE", qty_on_hand=1)

    with pytest.raises(InsufficientStock):
        reserve_lines(
            checkout_id="rt-partial-0001",
            lines=[{"variant_id": plenty.pk, "qty": 2}, {"variant_id": scarce.pk, "qty": 5}],
        )

    assert StockRecord.objects.get(variant=plenty).qty_reserved == 0
    assert StockRecord.objects.get(variant=scarce).qty_reserved == 0


@pytest.mark.django_db(transaction=True)
def test_commit_over_http_writes_the_audit_row(service_provider):
    variant = _stocked_variant(sku="RT-COMMIT", qty_on_hand=10)
    reserve_lines(checkout_id="rt-commit-0001", lines=[{"variant_id": variant.pk, "qty": 4}])

    committed = commit_holds(checkout_id="rt-commit-0001", order_no="MD-RT-1")

    assert committed == {variant.pk: 4}
    record = StockRecord.objects.get(variant=variant)
    assert record.qty_on_hand == 6
    assert record.qty_reserved == 0
    movement = StockMovement.objects.get(variant=variant, reason=MovementReason.SALE)
    assert movement.delta == -4


@pytest.mark.django_db(transaction=True)
def test_release_over_http_returns_units_to_availability(service_provider):
    variant = _stocked_variant(sku="RT-RELEASE", qty_on_hand=10)
    reserve_lines(checkout_id="rt-release-0001", lines=[{"variant_id": variant.pk, "qty": 6}])
    assert StockRecord.objects.get(variant=variant).qty_reserved == 6

    assert release_holds(checkout_id="rt-release-0001") == 1

    record = StockRecord.objects.get(variant=variant)
    assert record.qty_reserved == 0
    assert record.qty_on_hand == 10, "a release is not a sale"


@pytest.mark.django_db(transaction=True)
def test_release_of_an_unknown_checkout_id_succeeds(service_provider):
    """Compensation runs where the caller cannot know its reserve landed."""
    assert release_holds(checkout_id="rt-never-existed-0001") == 0


@pytest.mark.django_db(transaction=True)
def test_replayed_reserve_does_not_double_count(service_provider):
    """The idempotency protocol, end to end and against real rows.

    This is the case the whole protocol exists for: a retry that the client
    could not distinguish from a first attempt must not hold stock twice.
    """
    variant = _stocked_variant(sku="RT-REPLAY", qty_on_hand=10)
    lines = [{"variant_id": variant.pk, "qty": 3}]

    first = reserve_lines(checkout_id="rt-replay-0001", lines=lines)
    second = reserve_lines(checkout_id="rt-replay-0001", lines=lines)

    assert [row.pk for row in second] == [row.pk for row in first]
    assert StockRecord.objects.get(variant=variant).qty_reserved == 3
    assert Reservation.objects.filter(checkout_id="rt-replay-0001").count() == 1


@pytest.mark.django_db(transaction=True)
def test_replayed_commit_does_not_double_decrement(service_provider):
    variant = _stocked_variant(sku="RT-RECOMMIT", qty_on_hand=10)
    reserve_lines(checkout_id="rt-recommit-0001", lines=[{"variant_id": variant.pk, "qty": 2}])

    commit_holds(checkout_id="rt-recommit-0001", order_no="MD-RT-2")
    commit_holds(checkout_id="rt-recommit-0001", order_no="MD-RT-2")

    assert StockRecord.objects.get(variant=variant).qty_on_hand == 8
    assert StockMovement.objects.filter(variant=variant).count() == 1


@pytest.mark.django_db(transaction=True)
def test_batch_read_over_http_matches_the_ledger(service_provider):
    stocked = _stocked_variant(sku="RT-BATCH", qty_on_hand=7)
    unstocked = ProductVariant.objects.create(
        product=stocked.product, sku="RT-NOSTOCK", size=Size.L, color="RT-NOSTOCK", fit=Fit.REGULAR
    )

    records = get_stock_records([stocked.pk, unstocked.pk])

    assert records[stocked.pk].available == 7
    # Absent server-side, filled in client-side as zero — same answer the
    # in-process provider gives for a variant that was never stocked.
    assert records[unstocked.pk].available == 0
