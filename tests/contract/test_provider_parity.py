"""Provider equivalence: the same scenarios, both providers, identical results.

ADR-P3-005's rule is "never flip a default until parity". This file is what
turns that from an assertion into evidence. Every test runs twice — once
in-process, once over HTTP against the real ledger — and asserts the same
observable state, so "the service behaves like `local`" is checked rather than
believed.

This is precisely what ADR-P3-002's revert would have been prevented by: the
earlier extraction replaced the row-locked implementation outright and broke
Hard Invariants 1 and 4, and nothing compared the two.

`transaction=True` throughout: the ledger reads on its own connection and
cannot see an uncommitted Django transaction.
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


@pytest.fixture(params=["local", "service"])
def any_provider(request, settings):
    """Run the test body once per provider.

    The parametrisation *is* the parity proof — a scenario that only holds for
    one implementation fails here rather than in production after a cutover.
    """
    if request.param == "service":
        request.getfixturevalue("service_provider")
    else:
        request.getfixturevalue("db")
        settings.INVENTORY_PROVIDER = "local"
    return request.param


def _variant(*, sku, qty_on_hand=10):
    category, _ = Category.objects.get_or_create(name="Parity", slug="parity")
    product, _ = Product.objects.get_or_create(
        name="Parity Product",
        slug="parity-product",
        defaults={"category": category, "base_price": 100_00},
    )
    variant = ProductVariant.objects.create(
        product=product, sku=sku, size=Size.M, color=sku, fit=Fit.REGULAR
    )
    StockRecord.objects.create(variant=variant, qty_on_hand=qty_on_hand, qty_reserved=0)
    return variant


@pytest.mark.django_db(transaction=True)
def test_reserve_holds_units_without_consuming_them(any_provider):
    """A hold moves `qty_reserved` and never `qty_on_hand`."""
    variant = _variant(sku=f"PAR-RES-{any_provider}", qty_on_hand=10)

    reserve_lines(
        checkout_id=f"par-res-{any_provider}", lines=[{"variant_id": variant.pk, "qty": 3}]
    )

    record = StockRecord.objects.get(variant=variant)
    assert (record.qty_on_hand, record.qty_reserved, record.available) == (10, 3, 7)


@pytest.mark.django_db(transaction=True)
def test_reserve_beyond_availability_leaves_no_trace(any_provider):
    """Hard Invariant 1, and no partial write behind the rejection."""
    variant = _variant(sku=f"PAR-OVER-{any_provider}", qty_on_hand=2)
    checkout_id = f"par-over-{any_provider}"

    with pytest.raises(InsufficientStock):
        reserve_lines(checkout_id=checkout_id, lines=[{"variant_id": variant.pk, "qty": 5}])

    record = StockRecord.objects.get(variant=variant)
    assert (record.qty_on_hand, record.qty_reserved) == (2, 0)
    assert not Reservation.objects.filter(checkout_id=checkout_id).exists()


@pytest.mark.django_db(transaction=True)
def test_multi_line_reserve_is_all_or_nothing(any_provider):
    plenty = _variant(sku=f"PAR-OK-{any_provider}", qty_on_hand=10)
    scarce = _variant(sku=f"PAR-SHORT-{any_provider}", qty_on_hand=1)

    with pytest.raises(InsufficientStock):
        reserve_lines(
            checkout_id=f"par-multi-{any_provider}",
            lines=[{"variant_id": plenty.pk, "qty": 2}, {"variant_id": scarce.pk, "qty": 5}],
        )

    assert StockRecord.objects.get(variant=plenty).qty_reserved == 0
    assert StockRecord.objects.get(variant=scarce).qty_reserved == 0


@pytest.mark.django_db(transaction=True)
def test_commit_consumes_stock_and_writes_exactly_one_audit_row(any_provider):
    """Hard Invariant 4: every sale leaves one, and only one, ledger entry."""
    variant = _variant(sku=f"PAR-COMMIT-{any_provider}", qty_on_hand=10)
    checkout_id = f"par-commit-{any_provider}"
    reserve_lines(checkout_id=checkout_id, lines=[{"variant_id": variant.pk, "qty": 4}])

    committed = commit_holds(checkout_id=checkout_id, order_no="MD-PAR-1")

    assert committed == {variant.pk: 4}
    record = StockRecord.objects.get(variant=variant)
    assert (record.qty_on_hand, record.qty_reserved) == (6, 0)
    movements = StockMovement.objects.filter(variant=variant, reason=MovementReason.SALE)
    assert movements.count() == 1
    assert movements.first().delta == -4


@pytest.mark.django_db(transaction=True)
def test_release_returns_units_and_is_not_a_sale(any_provider):
    variant = _variant(sku=f"PAR-REL-{any_provider}", qty_on_hand=10)
    checkout_id = f"par-rel-{any_provider}"
    reserve_lines(checkout_id=checkout_id, lines=[{"variant_id": variant.pk, "qty": 6}])

    assert release_holds(checkout_id=checkout_id) == 1

    record = StockRecord.objects.get(variant=variant)
    assert (record.qty_on_hand, record.qty_reserved) == (10, 0)
    assert not StockMovement.objects.filter(variant=variant).exists()


@pytest.mark.django_db(transaction=True)
def test_release_of_unknown_checkout_id_is_a_no_op(any_provider):
    assert release_holds(checkout_id=f"par-absent-{any_provider}") == 0


@pytest.mark.django_db(transaction=True)
def test_replayed_reserve_holds_once(any_provider):
    variant = _variant(sku=f"PAR-REPLAY-{any_provider}", qty_on_hand=10)
    checkout_id = f"par-replay-{any_provider}"
    lines = [{"variant_id": variant.pk, "qty": 3}]

    reserve_lines(checkout_id=checkout_id, lines=lines)
    reserve_lines(checkout_id=checkout_id, lines=lines)

    assert StockRecord.objects.get(variant=variant).qty_reserved == 3
    assert Reservation.objects.filter(checkout_id=checkout_id).count() == 1


@pytest.mark.django_db(transaction=True)
def test_replayed_commit_decrements_once(any_provider):
    """A retried payment webhook must not sell the same units twice."""
    variant = _variant(sku=f"PAR-RECOMMIT-{any_provider}", qty_on_hand=10)
    checkout_id = f"par-recommit-{any_provider}"
    reserve_lines(checkout_id=checkout_id, lines=[{"variant_id": variant.pk, "qty": 2}])

    commit_holds(checkout_id=checkout_id, order_no="MD-PAR-2")
    commit_holds(checkout_id=checkout_id, order_no="MD-PAR-2")

    assert StockRecord.objects.get(variant=variant).qty_on_hand == 8
    assert StockMovement.objects.filter(variant=variant).count() == 1


@pytest.mark.django_db(transaction=True)
def test_committed_hold_cannot_then_be_released(any_provider):
    """A sale is terminal: releasing it would resurrect sold stock."""
    variant = _variant(sku=f"PAR-TERM-{any_provider}", qty_on_hand=10)
    checkout_id = f"par-term-{any_provider}"
    reserve_lines(checkout_id=checkout_id, lines=[{"variant_id": variant.pk, "qty": 2}])
    commit_holds(checkout_id=checkout_id, order_no="MD-PAR-3")

    assert release_holds(checkout_id=checkout_id) == 0

    record = StockRecord.objects.get(variant=variant)
    assert (record.qty_on_hand, record.qty_reserved) == (8, 0)


@pytest.mark.django_db(transaction=True)
def test_batch_read_reports_availability_identically(any_provider):
    stocked = _variant(sku=f"PAR-BATCH-{any_provider}", qty_on_hand=7)
    unstocked = ProductVariant.objects.create(
        product=stocked.product,
        sku=f"PAR-NOSTOCK-{any_provider}",
        size=Size.L,
        color=f"PAR-NOSTOCK-{any_provider}",
        fit=Fit.REGULAR,
    )
    reserve_lines(
        checkout_id=f"par-batch-{any_provider}", lines=[{"variant_id": stocked.pk, "qty": 2}]
    )

    records = get_stock_records([stocked.pk, unstocked.pk])

    assert records[stocked.pk].available == 5, "availability is on-hand minus reserved"
    assert records[unstocked.pk].available == 0


@pytest.mark.django_db(transaction=True)
def test_reservation_rows_carry_the_checkout_id(any_provider):
    """Both providers key holds the same way, so compensation is portable."""
    variant = _variant(sku=f"PAR-KEY-{any_provider}", qty_on_hand=10)
    checkout_id = f"par-key-{any_provider}"

    reserve_lines(checkout_id=checkout_id, lines=[{"variant_id": variant.pk, "qty": 1}])

    held = Reservation.objects.get(checkout_id=checkout_id)
    assert held.status == ReservationStatus.ACTIVE
    assert held.variant_id == variant.pk


# --- Operations that were stubs until ADR-P3-021 ----------------------------


@pytest.mark.django_db(transaction=True)
def test_adjust_stock_restocks_with_an_audit_row(any_provider):
    """A merchant must be able to restock under either provider.

    This raised outright under `service` — one of the gaps ADR-P3-002 reverted
    over, and invisible to any suite that only exercised `local`.
    """
    from apps.inventory.services import adjust_stock

    variant = _variant(sku=f"PAR-ADJ-{any_provider}", qty_on_hand=4)

    adjust_stock(variant_id=variant.pk, delta=6, reason=MovementReason.RESTOCK)

    assert StockRecord.objects.get(variant=variant).qty_on_hand == 10
    movement = StockMovement.objects.get(variant=variant, reason=MovementReason.RESTOCK)
    assert movement.delta == 6


@pytest.mark.django_db(transaction=True)
def test_adjust_stock_cannot_push_on_hand_below_reserved(any_provider):
    """Hard Invariant 1 again, from the adjustment side."""
    from apps.inventory.exceptions import InvalidStockAdjustment
    from apps.inventory.services import adjust_stock

    variant = _variant(sku=f"PAR-ADJDOWN-{any_provider}", qty_on_hand=10)
    reserve_lines(
        checkout_id=f"par-adjdown-{any_provider}", lines=[{"variant_id": variant.pk, "qty": 8}]
    )

    with pytest.raises(InvalidStockAdjustment):
        adjust_stock(variant_id=variant.pk, delta=-5, reason=MovementReason.ADJUSTMENT)

    record = StockRecord.objects.get(variant=variant)
    assert (record.qty_on_hand, record.qty_reserved) == (10, 8)


@pytest.mark.django_db(transaction=True)
def test_expired_holds_are_swept_back_to_availability(any_provider):
    """Under `service` this returned 0 unconditionally, so holds never expired.

    An abandoned cart would have kept its stock permanently — the failure is
    silent, and only shows up as inventory that cannot be sold.
    """
    import datetime

    from django.utils import timezone

    from apps.inventory.services import release_expired_reservations

    variant = _variant(sku=f"PAR-SWEEP-{any_provider}", qty_on_hand=10)
    checkout_id = f"par-sweep-{any_provider}"
    reserve_lines(checkout_id=checkout_id, lines=[{"variant_id": variant.pk, "qty": 4}])
    Reservation.objects.filter(checkout_id=checkout_id).update(
        expires_at=timezone.now() - datetime.timedelta(minutes=1)
    )

    assert release_expired_reservations() == 1

    record = StockRecord.objects.get(variant=variant)
    assert (record.qty_on_hand, record.qty_reserved) == (10, 0)
    assert Reservation.objects.get(checkout_id=checkout_id).status == ReservationStatus.EXPIRED


@pytest.mark.django_db(transaction=True)
def test_low_stock_scan_reports_skus_not_bare_ids(any_provider):
    """The alert email renders `record.variant.sku`.

    Under `service` the scan returned `[]`, so alerting stopped silently; a
    naive fix would have returned integers and quietly changed every alert
    from SKUs to numbers. Both providers must yield the same readable shape.
    """
    from apps.inventory.services import scan_low_stock

    variant = _variant(sku=f"PAR-LOW-{any_provider}", qty_on_hand=2)
    StockRecord.objects.filter(variant=variant).update(low_stock_threshold=5)

    flagged = list(scan_low_stock())

    skus = {row.variant.sku for row in flagged}
    assert variant.sku in skus, f"expected {variant.sku} among {skus}"
