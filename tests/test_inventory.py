"""Inventory core contracts (Epic B): atomic reservations under real InnoDB
concurrency, TTL expiry, the append-only audit trail, and the low-stock scan.

The two threaded tests are release gates (§3.1, M2): they must run on MySQL —
engines without real row locks would serialize them into meaninglessness.
"""

import datetime
from queue import Queue
from threading import Barrier, Thread

import pytest
from django.core import mail
from django.db import connections
from django.test import override_settings
from django.utils import timezone

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
    InvalidReservationState,
    InvalidStockAdjustment,
    adjust_stock,
    commit_reservation,
    release_expired_reservations,
    release_reservation,
    reserve_stock,
    scan_low_stock,
)
from apps.notifications.services import send_low_stock_alert
from apps.orders.models import Order
from apps.orders.services import next_order_no
from jobs.scheduler import build_scheduler


def _create_stocked_variant(*, sku="RACE-SKU", qty_on_hand=10, low_stock_threshold=5):
    """Committed catalog + stock fixture shared by every contract in this module."""
    category, _ = Category.objects.get_or_create(name="Race Test", slug="race-test")
    product, _ = Product.objects.get_or_create(
        name="Race Test Product",
        slug="race-test-product",
        defaults={"category": category, "base_price": 100_00},
    )
    variant = ProductVariant.objects.create(
        product=product,
        sku=sku,
        size=Size.M,
        color=f"Black-{sku}",  # unique axes per SKU under uniq_variant_axes
        fit=Fit.REGULAR,
    )
    StockRecord.objects.create(
        variant=variant,
        qty_on_hand=qty_on_hand,
        qty_reserved=0,
        low_stock_threshold=low_stock_threshold,
    )
    return variant


def _run_parallel_buyers(variant_id, buyer_count):
    """Race `buyer_count` single-unit reservations on independent MySQL connections."""
    # The barrier aligns all attempts closely enough to exercise InnoDB row locking.
    start_together = Barrier(buyer_count)
    # A thread-safe queue records business outcomes and unexpected worker exceptions.
    outcomes = Queue()

    def buyer():
        # Django connections are thread-local; closing first guarantees a fresh session.
        connections.close_all()
        try:
            start_together.wait(timeout=15)
            reserve_stock(variant_id=variant_id, qty=1)
        except InsufficientStock:
            # Losing because stock is already reserved is the expected business rejection.
            outcomes.put("insufficient")
        except BaseException as error:  # noqa: BLE001
            # Preserve worker failures for an assertion in the main pytest thread.
            outcomes.put(error)
        else:
            outcomes.put("reserved")
        finally:
            # Do not leak thread-owned connections into later tests.
            connections.close_all()

    buyers = [Thread(target=buyer, name=f"buyer-{number}") for number in range(buyer_count)]
    for thread in buyers:
        thread.start()
    for thread in buyers:
        thread.join(timeout=60)

    # A deadlock or unbounded lock wait is itself a failed concurrency contract.
    assert all(not thread.is_alive() for thread in buyers)

    results = [outcomes.get_nowait() for _ in buyers]
    unexpected_errors = [result for result in results if isinstance(result, BaseException)]
    assert unexpected_errors == []
    return results


@pytest.mark.django_db(transaction=True)
def test_two_buyers_competing_for_one_unit_produce_exactly_one_success():
    """Two real MySQL connections may reserve one unit only once, with no oversell."""
    variant = _create_stocked_variant(qty_on_hand=1)

    results = _run_parallel_buyers(variant.pk, buyer_count=2)

    assert sorted(results) == ["insufficient", "reserved"]
    stock = StockRecord.objects.get(variant=variant)
    assert stock.qty_on_hand == 1
    assert stock.qty_reserved == 1
    assert stock.available == 0


@pytest.mark.django_db(transaction=True)
def test_m2_gate_twenty_buyers_for_ten_units_produce_exactly_ten_successes():
    """M2 release gate (§10): 20 parallel buys of 10 units → exactly 10 wins, 0 oversells."""
    variant = _create_stocked_variant(qty_on_hand=10)

    results = _run_parallel_buyers(variant.pk, buyer_count=20)

    assert results.count("reserved") == 10
    assert results.count("insufficient") == 10
    stock = StockRecord.objects.get(variant=variant)
    assert stock.qty_on_hand == 10
    assert stock.qty_reserved == 10
    assert stock.available == 0
    assert Reservation.objects.filter(status=ReservationStatus.ACTIVE).count() == 10
    # Reservations are holds, not sales: the audit ledger must remain empty.
    assert StockMovement.objects.count() == 0


@pytest.mark.django_db
def test_reserve_creates_active_hold_with_configured_ttl():
    variant = _create_stocked_variant()

    before = timezone.now()
    reservation = reserve_stock(variant_id=variant.pk, qty=3, session_key="cart-abc")
    after = timezone.now()

    assert reservation.status == ReservationStatus.ACTIVE
    assert reservation.qty == 3
    assert reservation.session_key == "cart-abc"
    # FR-5: the hold must expire 15 minutes out (bounded by the call window).
    assert before + datetime.timedelta(minutes=15) <= reservation.expires_at
    assert reservation.expires_at <= after + datetime.timedelta(minutes=15)

    stock = StockRecord.objects.get(variant=variant)
    assert (stock.qty_on_hand, stock.qty_reserved, stock.available) == (10, 3, 7)
    assert StockMovement.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("bad_qty", [0, -1, True, 1.5, "1"])
def test_reserve_rejects_non_positive_or_non_integer_qty(bad_qty):
    variant = _create_stocked_variant()

    with pytest.raises(ValueError):
        reserve_stock(variant_id=variant.pk, qty=bad_qty)
    assert Reservation.objects.count() == 0


@pytest.mark.django_db
def test_reserve_beyond_availability_leaves_no_trace():
    variant = _create_stocked_variant()
    reserve_stock(variant_id=variant.pk, qty=8)

    with pytest.raises(InsufficientStock):
        reserve_stock(variant_id=variant.pk, qty=3)

    stock = StockRecord.objects.get(variant=variant)
    assert stock.qty_reserved == 8
    assert Reservation.objects.count() == 1


@pytest.mark.django_db
def test_reserve_unknown_variant_fails_loudly():
    # An untracked SKU must never be sellable (no silent zero-stock default).
    with pytest.raises(StockRecord.DoesNotExist):
        reserve_stock(variant_id=999_999, qty=1)


@pytest.mark.django_db
def test_release_returns_units_and_is_idempotent():
    variant = _create_stocked_variant()
    reservation = reserve_stock(variant_id=variant.pk, qty=4)

    released = release_reservation(reservation.pk)
    assert released.status == ReservationStatus.RELEASED
    assert released.ended_at is not None
    stock = StockRecord.objects.get(variant=variant)
    assert (stock.qty_reserved, stock.available) == (0, 10)

    # The abandon path and the TTL sweep may race; the loser must be a no-op.
    again = release_reservation(reservation.pk)
    assert again.status == ReservationStatus.RELEASED
    assert StockRecord.objects.get(variant=variant).qty_reserved == 0
    assert StockMovement.objects.count() == 0


@pytest.mark.django_db
def test_commit_converts_hold_into_sale_with_audit_row():
    variant = _create_stocked_variant()
    reservation = reserve_stock(variant_id=variant.pk, qty=2)
    order = Order.objects.create(order_no=next_order_no())

    committed = commit_reservation(reservation_id=reservation.pk, order=order)

    assert committed.status == ReservationStatus.COMMITTED
    assert committed.order == order
    stock = StockRecord.objects.get(variant=variant)
    assert (stock.qty_on_hand, stock.qty_reserved, stock.available) == (8, 0, 8)

    movement = StockMovement.objects.get()
    assert movement.delta == -2
    assert movement.reason == MovementReason.SALE
    assert movement.ref_order == order

    # A sale is final: neither a second commit nor a release may touch it.
    with pytest.raises(InvalidReservationState):
        commit_reservation(reservation_id=reservation.pk, order=order)
    with pytest.raises(InvalidReservationState):
        release_reservation(reservation.pk)


@pytest.mark.django_db
def test_commit_honors_active_hold_even_past_expiry():
    """The sweep alone expires holds; a paid-but-late shopper keeps their units."""
    variant = _create_stocked_variant()
    reservation = reserve_stock(variant_id=variant.pk, qty=1)
    Reservation.objects.filter(pk=reservation.pk).update(
        expires_at=timezone.now() - datetime.timedelta(minutes=1)
    )
    order = Order.objects.create(order_no=next_order_no())

    committed = commit_reservation(reservation_id=reservation.pk, order=order)

    assert committed.status == ReservationStatus.COMMITTED
    assert StockRecord.objects.get(variant=variant).qty_on_hand == 9


@pytest.mark.django_db
def test_sweep_expires_only_overdue_active_holds():
    variant = _create_stocked_variant()
    overdue = reserve_stock(variant_id=variant.pk, qty=2)
    fresh = reserve_stock(variant_id=variant.pk, qty=3)
    Reservation.objects.filter(pk=overdue.pk).update(
        expires_at=timezone.now() - datetime.timedelta(seconds=1)
    )

    expired_count = release_expired_reservations()

    assert expired_count == 1
    overdue.refresh_from_db()
    fresh.refresh_from_db()
    assert overdue.status == ReservationStatus.EXPIRED
    assert fresh.status == ReservationStatus.ACTIVE
    stock = StockRecord.objects.get(variant=variant)
    # Only the overdue hold's units returned; expiry is not a stock movement.
    assert (stock.qty_reserved, stock.available) == (3, 7)
    assert StockMovement.objects.count() == 0


@pytest.mark.django_db
def test_adjust_stock_writes_counter_and_ledger_together():
    variant = _create_stocked_variant()

    stock = adjust_stock(variant_id=variant.pk, delta=5, reason=MovementReason.RESTOCK)

    assert stock.qty_on_hand == 15
    movement = StockMovement.objects.get()
    assert (movement.delta, movement.reason) == (5, MovementReason.RESTOCK)


@pytest.mark.django_db
def test_adjust_stock_rejects_invalid_requests():
    variant = _create_stocked_variant()
    reserve_stock(variant_id=variant.pk, qty=5)

    with pytest.raises(InvalidStockAdjustment):
        adjust_stock(variant_id=variant.pk, delta=0, reason=MovementReason.ADJUSTMENT)
    with pytest.raises(InvalidStockAdjustment):
        adjust_stock(variant_id=variant.pk, delta=-1, reason=MovementReason.RESTOCK)
    with pytest.raises(InvalidStockAdjustment):
        # Sales exist only as committed reservations (single writer of the ledger).
        adjust_stock(variant_id=variant.pk, delta=-1, reason=MovementReason.SALE)
    with pytest.raises(InvalidStockAdjustment):
        # 10 − 6 = 4 on hand would strand the 5 units already promised to holds.
        adjust_stock(variant_id=variant.pk, delta=-6, reason=MovementReason.ADJUSTMENT)

    stock = StockRecord.objects.get(variant=variant)
    assert (stock.qty_on_hand, stock.qty_reserved) == (10, 5)
    assert StockMovement.objects.count() == 0


@pytest.mark.django_db
def test_scan_low_stock_measures_availability_not_shelf_count():
    variant = _create_stocked_variant(qty_on_hand=10, low_stock_threshold=5)

    # 10 available > 5 threshold: healthy.
    assert list(scan_low_stock()) == []

    # Same shelf count, but holds shrink availability to the threshold.
    reserve_stock(variant_id=variant.pk, qty=5)
    flagged = list(scan_low_stock())
    assert [record.variant_id for record in flagged] == [variant.pk]


@pytest.mark.django_db
@override_settings(LOW_STOCK_ALERT_RECIPIENTS=["ops@metrodrip.example"])
def test_low_stock_alert_emails_flagged_skus():
    variant = _create_stocked_variant(qty_on_hand=2, low_stock_threshold=5)

    sent = send_low_stock_alert(scan_low_stock())

    assert sent == 1
    assert len(mail.outbox) == 1
    assert variant.sku in mail.outbox[0].body


@pytest.mark.django_db
@override_settings(LOW_STOCK_ALERT_RECIPIENTS=[])
def test_low_stock_alert_degrades_to_noop_without_recipients():
    _create_stocked_variant(qty_on_hand=2, low_stock_threshold=5)

    assert send_low_stock_alert(scan_low_stock()) == 0
    assert mail.outbox == []


def test_scheduler_registers_both_inventory_jobs():
    scheduler = build_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"reservation-sweep", "low-stock-scan"}
