"""Stock holds: the Orders-side receipt that replaced a reverse FK into the ledger.

The defect these pin (ADR-P3-012): both payment providers consumed stock by
iterating `order.reservations.filter(status="active")`, a reverse foreign key
into `inventory_reservation`. That resolves only while Orders and the ledger
share one schema. Against a separate ledger it returns empty, the commit loop
does nothing, and the shortfall pass re-reserves and re-commits every line —
so the payment succeeds, `qty_on_hand` never moves, and no `StockMovement` is
written. Hard Invariant 4 failing silently on the money path.
"""

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import (
    MovementReason,
    Reservation,
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
from apps.orders.models import OrderStatus, StockHold, StockHoldState
from apps.shipping.models import ShippingZone


def _variant(*, sku="HOLD-SKU", qty_on_hand=10, price=100_00):
    category, _ = Category.objects.get_or_create(name="Holds", slug="holds")
    product, _ = Product.objects.get_or_create(
        name="Holds Product",
        slug="holds-product",
        defaults={"category": category, "base_price": price},
    )
    # `uniq_variant_axes` covers (product, size, color, fit), so tests that need
    # two variants of one product must differ on an axis — keying colour to the
    # SKU keeps every fixture in this module distinct without extra arguments.
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


# --- The ledger primitives, keyed by checkout_id ----------------------------


@pytest.mark.django_db
def test_reserve_lines_is_all_or_nothing():
    """A cart that cannot be fully held must hold nothing at all."""
    plenty = _variant(sku="HOLD-OK", qty_on_hand=10)
    scarce = _variant(sku="HOLD-SHORT", qty_on_hand=1)

    with pytest.raises(InsufficientStock):
        reserve_lines(
            checkout_id="checkout-partial-1",
            lines=[{"variant_id": plenty.pk, "qty": 2}, {"variant_id": scarce.pk, "qty": 5}],
        )

    assert StockRecord.objects.get(variant=plenty).qty_reserved == 0
    assert StockRecord.objects.get(variant=scarce).qty_reserved == 0
    assert Reservation.objects.filter(checkout_id="checkout-partial-1").count() == 0


@pytest.mark.django_db
def test_reserve_lines_replay_returns_the_same_holds():
    """Re-issuing one checkout_id must not double-reserve."""
    variant = _variant(sku="HOLD-REPLAY", qty_on_hand=10)
    lines = [{"variant_id": variant.pk, "qty": 3}]

    first = reserve_lines(checkout_id="checkout-replay-1", lines=lines)
    second = reserve_lines(checkout_id="checkout-replay-1", lines=lines)

    assert len(first) == 1
    assert [r.pk for r in second] == [r.pk for r in first]
    assert StockRecord.objects.get(variant=variant).qty_reserved == 3


@pytest.mark.django_db
def test_release_holds_is_a_no_op_for_an_unknown_checkout_id():
    """Compensation runs where the caller cannot know a reserve landed."""
    assert release_holds(checkout_id="never-existed") == 0


@pytest.mark.django_db
def test_commit_holds_returns_per_variant_totals_and_writes_the_ledger():
    variant = _variant(sku="HOLD-COMMIT", qty_on_hand=10)
    reserve_lines(checkout_id="checkout-commit-1", lines=[{"variant_id": variant.pk, "qty": 4}])

    committed = commit_holds(checkout_id="checkout-commit-1")

    assert committed == {variant.pk: 4}
    record = StockRecord.objects.get(variant=variant)
    assert record.qty_on_hand == 6
    assert record.qty_reserved == 0
    movement = StockMovement.objects.get(variant=variant, reason=MovementReason.SALE)
    assert movement.delta == -4


@pytest.mark.django_db
def test_commit_holds_replay_commits_nothing_further():
    """A replayed payment webhook must not decrement stock twice."""
    variant = _variant(sku="HOLD-IDEM", qty_on_hand=10)
    reserve_lines(checkout_id="checkout-idem-1", lines=[{"variant_id": variant.pk, "qty": 2}])

    assert commit_holds(checkout_id="checkout-idem-1") == {variant.pk: 2}
    assert commit_holds(checkout_id="checkout-idem-1") == {}

    assert StockRecord.objects.get(variant=variant).qty_on_hand == 8
    assert StockMovement.objects.filter(variant=variant).count() == 1


@pytest.mark.django_db
def test_batch_read_answers_every_id_including_unstocked_ones():
    """One call, and a variant with no StockRecord reads as zero rather than raising."""
    stocked = _variant(sku="HOLD-BATCH-1", qty_on_hand=7)
    unstocked = ProductVariant.objects.create(
        product=stocked.product,
        sku="HOLD-BATCH-2",
        size=Size.L,
        color="HOLD-BATCH-2",
        fit=Fit.REGULAR,
    )

    records = get_stock_records([stocked.pk, unstocked.pk, stocked.pk])

    assert records[stocked.pk].available == 7
    assert records[unstocked.pk].available == 0


# --- The money path ---------------------------------------------------------


@pytest.mark.django_db
def test_checkout_records_a_stock_hold_for_the_order():
    """Orders must own a receipt for the stock it asked the ledger to hold."""
    from apps.orders.checkout import place_order

    variant = _variant(sku="HOLD-CHECKOUT", qty_on_hand=10)
    order, _ = place_order(
        items=[{"variant_id": variant.pk, "qty": 2}],
        zone_id=_zone().pk,
        contact={"name": "Ada", "email": "ada@example.test"},
        success_url="https://example.test/ok",
        cancel_url="https://example.test/no",
    )

    hold = StockHold.objects.get(order=order)
    assert hold.state == StockHoldState.ACTIVE
    assert hold.checkout_id
    # The ledger's rows carry the same identity, so either side can act on it.
    assert Reservation.objects.filter(checkout_id=hold.checkout_id).count() == 1


@pytest.mark.django_db
@override_settings(PAYMENT_PROVIDER="simulated")
def test_paid_order_decrements_stock_and_writes_one_audit_row(client):
    """The regression: paying must move qty_on_hand and leave audit evidence.

    Under the previous reverse-FK loop this passed only because Orders and the
    ledger shared a schema. It is asserted here against the hold receipt, so it
    keeps meaning the same thing when the ledger moves.
    """
    from apps.orders.checkout import place_order

    variant = _variant(sku="HOLD-PAID", qty_on_hand=10)
    order, _ = place_order(
        items=[{"variant_id": variant.pk, "qty": 3}],
        zone_id=_zone().pk,
        contact={"name": "Ada", "email": "ada@example.test"},
        success_url="https://example.test/ok",
        cancel_url="https://example.test/no",
    )

    from apps.payments.services import confirm_order_paid

    assert confirm_order_paid(order=order) is True

    order.refresh_from_db()
    assert order.status == OrderStatus.PAID

    record = StockRecord.objects.get(variant=variant)
    assert record.qty_on_hand == 7, "payment must consume physical stock"
    assert record.qty_reserved == 0, "the hold must not survive the sale"

    movements = StockMovement.objects.filter(variant=variant, reason=MovementReason.SALE)
    assert movements.count() == 1, "exactly one audit row per sale (Invariant 4)"
    assert movements.first().delta == -3

    hold = StockHold.objects.get(order=order)
    assert hold.state == StockHoldState.COMMITTED
    assert hold.committed_at is not None


@pytest.mark.django_db
@override_settings(PAYMENT_PROVIDER="simulated")
def test_replayed_payment_never_double_decrements(client):
    from apps.orders.checkout import place_order
    from apps.payments.services import confirm_order_paid

    variant = _variant(sku="HOLD-REPLAY-PAID", qty_on_hand=10)
    order, _ = place_order(
        items=[{"variant_id": variant.pk, "qty": 2}],
        zone_id=_zone().pk,
        contact={"name": "Ada", "email": "ada@example.test"},
        success_url="https://example.test/ok",
        cancel_url="https://example.test/no",
    )

    assert confirm_order_paid(order=order) is True
    assert confirm_order_paid(order=order) is False

    assert StockRecord.objects.get(variant=variant).qty_on_hand == 8
    assert StockMovement.objects.filter(variant=variant).count() == 1


def test_payment_path_never_follows_a_reverse_fk_into_the_ledger():
    """Structural, because behaviour cannot catch this on one schema.

    While Orders and the ledger share a database, `order.reservations` resolves
    correctly and every behavioural test above passes with or without the fix.
    The bug only appears once the ledger is genuinely separate — which is
    exactly when it is most expensive to discover. So the property asserted is
    the one that actually matters: the paid path asks the ledger to act on a
    `checkout_id` it supplied, and never reads the ledger's rows itself.

    Walks the AST rather than grepping, so the prose in these modules
    describing the old bug does not itself trip the check.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    for module in (
        root / "apps" / "payments" / "providers" / "simulated.py",
        root / "apps" / "payments" / "providers" / "paymongo.py",
        root / "apps" / "payments" / "holds.py",
    ):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        offenders = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "reservations"
        ]
        assert not offenders, (
            f"{module.name}:{offenders} reads the stock ledger's rows directly; "
            "the paid path must go through StockHold + commit_holds(checkout_id=...)"
        )


@pytest.mark.django_db
def test_product_page_reads_stock_once_regardless_of_variant_count(client):
    """The N+1 fix, asserted by call count rather than by inspection.

    Under `INVENTORY_PROVIDER=service` every one of these reads is an HTTP
    round trip with its own timeout budget, so "one call per variant" on a
    page that lists every variant of a product is the difference between one
    request and dozens.
    """
    from unittest.mock import patch

    from apps.catalog.models import Category, Product

    category, _ = Category.objects.get_or_create(name="NPlusOne", slug="nplusone")
    product = Product.objects.create(
        name="Many Variants", slug="many-variants", category=category, base_price=100_00
    )
    sizes = [Size.XS, Size.S, Size.M, Size.L, Size.XL]
    for index, size in enumerate(sizes):
        variant = ProductVariant.objects.create(
            product=product, sku=f"NPO-{index}", size=size, color="Black", fit=Fit.REGULAR
        )
        StockRecord.objects.create(variant=variant, qty_on_hand=5)

    real = get_stock_records
    with patch("apps.storefront.views.get_stock_records", side_effect=real) as batched:
        response = client.get(reverse("storefront:product-detail", args=[product.slug]))

    assert response.status_code == 200
    assert batched.call_count == 1, (
        f"{len(sizes)} variants must cost one stock read, not {batched.call_count}"
    )


# --- ADR-P3-022: stock is secured before the order row exists ---------------


@pytest.mark.django_db
def test_sold_out_checkout_writes_nothing_at_all():
    """A rejected checkout must not leave an order, a line, or a burnt number.

    Under order-then-reserve this consumed an OrderNumberSequence value on
    every failed attempt — against a public format that allows only 99,999 a
    year — and briefly committed a `pending` order that held no stock.
    """
    from django.utils import timezone

    from apps.orders.checkout import place_order
    from apps.orders.models import Order, OrderItem, OrderNumberSequence

    variant = _variant(sku="ORDER-SOLDOUT", qty_on_hand=1)
    zone = _zone()
    year = timezone.now().year
    sequence_before = OrderNumberSequence.objects.filter(year=year).first()
    burnt_before = sequence_before.last_value if sequence_before else 0

    with pytest.raises(InsufficientStock):
        place_order(
            items=[{"variant_id": variant.pk, "qty": 5}],
            zone_id=zone.pk,
            contact={"name": "Ada", "email": "ada@example.test"},
            success_url="https://example.test/ok",
            cancel_url="https://example.test/no",
        )

    assert Order.objects.count() == 0, "no order may exist for stock that was never secured"
    assert OrderItem.objects.count() == 0
    assert StockHold.objects.count() == 0
    assert StockRecord.objects.get(variant=variant).qty_reserved == 0

    sequence_after = (
        OrderNumberSequence.objects.filter(year=sequence_before.year).first()
        if sequence_before
        else None
    )
    burnt_after = sequence_after.last_value if sequence_after else 0
    assert burnt_after == burnt_before, "a sold-out attempt must not consume an order number"


@pytest.mark.django_db
def test_payment_session_failure_cancels_the_order_and_frees_the_stock():
    """An unpayable order must not linger as `pending` holding stock.

    It previously stayed pending forever: visible in the merchant console
    indefinitely, and leaving open a window where a late webhook could pay an
    order that held nothing.
    """
    from unittest.mock import patch

    from apps.orders.checkout import PaymentSessionError, place_order
    from apps.orders.models import Order, OrderStatus

    variant = _variant(sku="ORDER-NOPAY", qty_on_hand=10)
    zone = _zone()

    with patch(
        "apps.orders.checkout.create_checkout_session",
        side_effect=RuntimeError("provider down"),
    ):
        with pytest.raises(PaymentSessionError):
            place_order(
                items=[{"variant_id": variant.pk, "qty": 3}],
                zone_id=zone.pk,
                contact={"name": "Ada", "email": "ada@example.test"},
                success_url="https://example.test/ok",
                cancel_url="https://example.test/no",
            )

    order = Order.objects.get()
    assert order.status == OrderStatus.CANCELLED
    assert StockRecord.objects.get(variant=variant).qty_reserved == 0, "holds must be returned"
    assert StockHold.objects.get(order=order).state == StockHoldState.RELEASED


@pytest.mark.django_db
def test_reserve_happens_before_any_order_row_is_written():
    """Structural: the ledger call must precede Order.objects.create.

    Ordering is the entire content of this change, and a refactor could
    reorder the two without any behavioural test noticing while stock happens
    to be plentiful.
    """
    import inspect

    from apps.orders import checkout

    source = inspect.getsource(checkout.place_order)
    assert source.index("reserve_lines(") < source.index("Order.objects.create("), (
        "stock must be secured before an order row exists (ADR-P3-022)"
    )


@pytest.mark.django_db
def test_stock_service_outage_is_not_reported_as_a_payment_failure():
    """A ledger outage and a payment outage are different incidents.

    Both are 502-class, but folding one into the other tells a shopper the
    wrong thing and sends whoever is on call to the wrong system.
    """
    from unittest.mock import patch

    from apps.inventory.services import ReservationUnavailable
    from apps.orders.checkout import place_order
    from apps.orders.models import Order

    variant = _variant(sku="ORDER-LEDGERDOWN", qty_on_hand=10)
    zone = _zone()

    with patch(
        "apps.orders.checkout.reserve_lines",
        side_effect=ReservationUnavailable("ledger unreachable"),
    ):
        with pytest.raises(ReservationUnavailable):
            place_order(
                items=[{"variant_id": variant.pk, "qty": 2}],
                zone_id=zone.pk,
                contact={"name": "Ada", "email": "ada@example.test"},
                success_url="https://example.test/ok",
                cancel_url="https://example.test/no",
            )

    # Nothing was written, because nothing had been written yet when it failed.
    assert Order.objects.count() == 0
    assert StockHold.objects.count() == 0
