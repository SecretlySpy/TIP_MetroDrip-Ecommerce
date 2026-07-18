"""Database contracts for the foundational MetroDrip domain models.

These tests deliberately use the configured MySQL test database. Several guarantees below
depend on MySQL 8 enforcing ``CHECK`` and ``UNIQUE`` constraints, so substituting SQLite would
make the suite prove behavior that production does not actually use.
"""

from io import StringIO
from itertools import count

import pytest
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction

from apps.accounts.models import Customer
from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import MovementReason, StockMovement, StockRecord
from apps.orders.models import IllegalTransition, Order, OrderItem, OrderStatus
from apps.payments.models import Payment, PaymentMethod
from apps.reviews.models import Review

# Every test in this module exercises model persistence or the production database mapping.
pytestmark = pytest.mark.django_db

# Monotonic IDs keep helper-created natural keys unique when one test needs several objects.
_catalog_ids = count(1)
_customer_ids = count(1)
_order_ids = count(1)


def _create_variant() -> ProductVariant:
    """Create the smallest valid catalog graph needed by order and inventory tests."""
    suffix = next(_catalog_ids)
    # A dedicated category avoids unrelated uniqueness errors obscuring the contract under test.
    category = Category.objects.create(name=f"Category {suffix}", slug=f"category-{suffix}")
    # Integer centavos are used here so fixtures also follow the no-float money invariant.
    product = Product.objects.create(
        name=f"Product {suffix}",
        slug=f"product-{suffix}",
        category=category,
        base_price=125_00,
    )
    # One concrete SKU is enough for quantity, review, and movement behavior.
    return ProductVariant.objects.create(
        product=product,
        sku=f"TEST-SKU-{suffix}",
        size=Size.M,
        color="Black",
        fit=Fit.REGULAR,
    )


def _create_customer() -> Customer:
    """Create a registered customer with a unique email address."""
    suffix = next(_customer_ids)
    return Customer.objects.create_user(
        email=f"shopper-{suffix}@example.com",
        password="test-only-password",
        name=f"Shopper {suffix}",
    )


def _create_order(*, customer: Customer | None = None) -> Order:
    """Create a pending order with a production-shaped unique order number."""
    suffix = next(_order_ids)
    return Order.objects.create(
        order_no=f"MD-2026-{suffix:05d}",
        customer=customer,
        shipping_address={"city": "Quezon City", "zone": "NCR"},
    )


def test_mysql_tables_use_innodb_and_utf8mb4():
    """The migrated test schema must preserve the storage-engine and Unicode invariants."""
    with connection.cursor() as cursor:
        # DATABASE() targets pytest's isolated schema, avoiding assumptions about
        # environment-specific test-database names.
        cursor.execute(
            """
            SELECT table_name, engine, table_collation
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_type = 'BASE TABLE'
              AND (engine <> 'InnoDB' OR table_collation NOT LIKE 'utf8mb4%%')
            ORDER BY table_name
            """
        )
        violations = cursor.fetchall()

    assert not violations


@pytest.mark.parametrize(
    ("model", "field_name"),
    [
        (Product, "base_price"),
        (ProductVariant, "price_override"),
        (Order, "subtotal"),
        (Order, "shipping_fee"),
        (Order, "total"),
        (OrderItem, "unit_price_snapshot"),
        (Payment, "amount"),
    ],
)
def test_money_fields_map_to_mysql_int_columns(model, field_name):
    """All centavo amounts must use MySQL INT rather than BIGINT or floating point."""
    field = model._meta.get_field(field_name)

    # PositiveIntegerField maps to an unsigned INT on the configured MySQL backend.
    assert field.get_internal_type() == "PositiveIntegerField"
    database_type = field.db_type(connection).lower()
    assert database_type.startswith("integer")
    assert "bigint" not in database_type


def test_passwordless_customer_is_an_account_not_a_guest_identity():
    """Guest ownership is represented by Order.customer=NULL, never a pseudo-account."""
    customer = Customer.objects.create_user(
        email="passwordless@example.com",
        password=None,
        name="Passwordless Account",
    )
    guest_order = _create_order()

    assert not customer.has_usable_password()
    assert not hasattr(customer, "is_guest")
    assert guest_order.customer_id is None


def test_superuser_requires_a_nonempty_password():
    """Administrative accounts must never be created in an unusable login state."""
    with pytest.raises(ValueError, match="non-empty password"):
        Customer.objects.create_superuser(
            email="admin@example.com",
            password="",
            name="Admin",
        )


def test_order_can_follow_the_complete_legal_lifecycle():
    """The sanctioned API persists every forward edge and the final refund edge."""
    order = _create_order()
    legal_path = [
        OrderStatus.PAID,
        OrderStatus.PACKED,
        OrderStatus.SHIPPED,
        OrderStatus.DELIVERED,
        OrderStatus.REFUNDED,
    ]

    for expected_status in legal_path:
        # transition_to is the sole public write path for an existing order's status.
        order.transition_to(expected_status)
        order.refresh_from_db()
        assert order.status == expected_status


def test_pending_order_can_be_cancelled():
    """Cancellation remains a legal terminal path for an order that was never paid."""
    order = _create_order()

    order.transition_to(OrderStatus.CANCELLED)

    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED


def test_illegal_order_transition_raises_without_changing_the_database():
    """Skipping directly from Pending to Shipped must fail atomically."""
    order = _create_order()

    with pytest.raises(IllegalTransition):
        order.transition_to(OrderStatus.SHIPPED)

    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING


def test_stale_order_instance_cannot_overwrite_a_newer_transition():
    """transition_to must lock and validate the database state, not stale Python state."""
    current = _create_order()
    stale = Order.objects.get(pk=current.pk)

    # The current writer moves Pending to Paid before the stale writer acts.
    current.transition_to(OrderStatus.PAID)

    # Pending to Cancelled looks legal to ``stale``, but Paid to Cancelled is forbidden.
    with pytest.raises(IllegalTransition):
        stale.transition_to(OrderStatus.CANCELLED)

    stale.refresh_from_db()
    assert stale.status == OrderStatus.PAID


def test_direct_order_status_save_is_rejected():
    """Assigning status and calling save cannot bypass the state-machine API."""
    order = _create_order()
    order.status = OrderStatus.PAID

    with pytest.raises(IllegalTransition):
        order.save(update_fields=["status"])

    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING


def test_explicit_primary_key_cannot_insert_a_non_pending_order():
    """A caller-supplied PK must not trick save() into treating a new row as existing."""
    order = Order(
        id=999_999,
        order_no="MD-2026-99998",
        status=OrderStatus.PAID,
        shipping_address={"city": "Quezon City", "zone": "NCR"},
    )

    with pytest.raises(IllegalTransition):
        order.save(force_insert=True)

    assert not Order.objects.filter(pk=order.pk).exists()


def test_queryset_order_status_update_is_rejected():
    """A bulk UPDATE must not provide a back door around transition_to's locking."""
    order = _create_order()

    with pytest.raises(IllegalTransition):
        Order.objects.filter(pk=order.pk).update(status=OrderStatus.PAID)

    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING


def test_order_conflict_upsert_cannot_modify_status():
    """MySQL ON DUPLICATE KEY UPDATE must not bypass the transition API."""
    existing = _create_order()
    conflicting = Order(order_no=existing.order_no, status=OrderStatus.PENDING)

    with pytest.raises(IllegalTransition):
        Order.objects.bulk_create(
            [conflicting],
            update_conflicts=True,
            update_fields=["status"],
            unique_fields=["order_no"],
        )

    existing.refresh_from_db()
    assert existing.status == OrderStatus.PENDING


def test_positional_order_conflict_upsert_cannot_modify_status():
    """Positional bulk options must pass through the same state-machine guard."""
    existing = _create_order()
    conflicting = Order(order_no=existing.order_no, status=OrderStatus.PENDING)

    with pytest.raises(IllegalTransition):
        Order.objects.bulk_create(
            [conflicting],
            None,  # batch_size
            False,  # ignore_conflicts
            True,  # update_conflicts
            ["status"],  # update_fields
            ["order_no"],  # unique_fields
        )

    existing.refresh_from_db()
    assert existing.status == OrderStatus.PENDING


def test_stale_plain_save_cannot_overwrite_concurrent_transition():
    """A save-all write must compare status while holding the same row lock."""
    current = _create_order()
    stale = Order.objects.get(pk=current.pk)
    current.transition_to(OrderStatus.PAID)
    stale.shipping_address = {"city": "Manila", "zone": "NCR"}

    with pytest.raises(IllegalTransition):
        stale.save()

    current.refresh_from_db()
    assert current.status == OrderStatus.PAID


def test_non_status_order_updates_remain_available():
    """The status guard should not prevent ordinary non-state order maintenance."""
    order = _create_order()

    updated_rows = Order.objects.filter(pk=order.pk).update(shipping_fee=150_00, total=150_00)

    order.refresh_from_db()
    assert updated_rows == 1
    assert order.shipping_fee == 150_00
    assert order.total == 150_00


def test_order_total_database_constraint_rejects_mismatch():
    """Subtotal plus shipping must reconcile exactly to total in centavos."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.create(
            order_no="MD-2026-99999",
            subtotal=100_00,
            shipping_fee=50_00,
            total=149_00,
            shipping_address={"city": "Quezon City", "zone": "NCR"},
        )


def test_payment_provider_reference_allows_multiple_nulls():
    """Uninitialized payments need NULL references without colliding with each other."""
    first = Payment.objects.create(
        order=_create_order(),
        provider_ref=None,
        method=PaymentMethod.CARD,
        amount=125_00,
    )
    second = Payment.objects.create(
        order=_create_order(),
        provider_ref=None,
        method=PaymentMethod.GCASH,
        amount=125_00,
    )

    assert first.provider_ref is None
    assert second.provider_ref is None


def test_payment_provider_reference_rejects_replay_duplicates():
    """A non-null PayMongo reference is an idempotency key and must be globally unique."""
    provider_ref = "paymongo-test-reference"
    Payment.objects.create(
        order=_create_order(),
        provider_ref=provider_ref,
        method=PaymentMethod.MAYA,
        amount=125_00,
    )

    # The inner savepoint contains MySQL's IntegrityError so the test transaction stays usable.
    with pytest.raises(IntegrityError), transaction.atomic():
        Payment.objects.create(
            order=_create_order(),
            provider_ref=provider_ref,
            method=PaymentMethod.CARD,
            amount=125_00,
        )


@pytest.mark.parametrize("invalid_rating", [0, 6])
def test_review_rating_database_constraint_rejects_out_of_range_values(invalid_rating):
    """Direct ORM writes cannot bypass the required inclusive 1..5 rating range."""
    customer = _create_customer()
    variant = _create_variant()
    order = _create_order(customer=customer)

    # Model validators do not run during create(), so failure here proves the DB constraint.
    with pytest.raises(IntegrityError), transaction.atomic():
        Review.objects.create(
            customer=customer,
            product=variant.product,
            order=order,
            rating=invalid_rating,
        )


@pytest.mark.parametrize("valid_rating", [1, 5])
def test_review_rating_database_constraint_accepts_range_boundaries(valid_rating):
    """The database check includes both documented endpoints."""
    customer = _create_customer()
    variant = _create_variant()
    review = Review.objects.create(
        customer=customer,
        product=variant.product,
        order=_create_order(customer=customer),
        rating=valid_rating,
    )

    assert review.rating == valid_rating


def test_order_item_quantity_database_constraint_rejects_zero():
    """PositiveIntegerField permits zero, so a separate CHECK must enforce qty >= 1."""
    order = _create_order()
    variant = _create_variant()

    with pytest.raises(IntegrityError), transaction.atomic():
        OrderItem.objects.create(order=order, variant=variant, qty=0, unit_price_snapshot=125_00)


def test_order_item_quantity_database_constraint_accepts_one():
    """A one-unit order line is the minimum valid purchase quantity."""
    item = OrderItem.objects.create(
        order=_create_order(),
        variant=_create_variant(),
        qty=1,
        unit_price_snapshot=125_00,
    )

    assert item.qty == 1


@pytest.mark.parametrize(
    ("delta", "reason"),
    [
        (0, MovementReason.ADJUSTMENT),
        (1, MovementReason.SALE),
        (-1, MovementReason.RESTOCK),
        (-1, MovementReason.RETURN),
    ],
)
def test_stock_movement_database_constraints_reject_zero_or_wrong_sign(delta, reason):
    """Ledger rows must be nonzero and agree with the inventory reason's direction."""
    variant = _create_variant()

    with pytest.raises(IntegrityError), transaction.atomic():
        StockMovement.objects.create(variant=variant, delta=delta, reason=reason)


@pytest.mark.parametrize(
    ("delta", "reason"),
    [
        (-1, MovementReason.SALE),
        (1, MovementReason.RESTOCK),
        (-1, MovementReason.ADJUSTMENT),
        (1, MovementReason.ADJUSTMENT),
        (1, MovementReason.RETURN),
    ],
)
def test_stock_movement_database_constraints_accept_valid_reason_signs(delta, reason):
    """Both adjustment directions and each directional business reason remain valid."""
    movement = StockMovement.objects.create(
        variant=_create_variant(),
        delta=delta,
        reason=reason,
    )

    assert movement.delta == delta


def test_stock_movement_instance_cannot_be_updated_or_deleted():
    """A persisted audit row is immutable through instance methods."""
    movement = StockMovement.objects.create(
        variant=_create_variant(),
        delta=3,
        reason=MovementReason.RESTOCK,
    )
    movement.delta = 4

    with pytest.raises(TypeError):
        movement.save(update_fields=["delta"])
    with pytest.raises(TypeError):
        movement.delete()

    movement.refresh_from_db()
    assert movement.delta == 3


def test_stock_movement_queryset_cannot_update_rows():
    """QuerySet.update must not bypass StockMovement.save's append-only guard."""
    movement = StockMovement.objects.create(
        variant=_create_variant(),
        delta=3,
        reason=MovementReason.RESTOCK,
    )

    with pytest.raises(TypeError):
        StockMovement.objects.filter(pk=movement.pk).update(delta=4)

    movement.refresh_from_db()
    assert movement.delta == 3


def test_stock_movement_queryset_cannot_delete_rows():
    """QuerySet.delete must not bypass StockMovement.delete's append-only guard."""
    movement = StockMovement.objects.create(
        variant=_create_variant(),
        delta=3,
        reason=MovementReason.RESTOCK,
    )

    with pytest.raises(TypeError):
        StockMovement.objects.filter(pk=movement.pk).delete()

    assert StockMovement.objects.filter(pk=movement.pk).exists()


def test_stock_movement_conflict_upsert_is_rejected():
    """Bulk conflict handling cannot translate an append into a historical rewrite."""
    movement = StockMovement.objects.create(
        variant=_create_variant(),
        delta=3,
        reason=MovementReason.RESTOCK,
    )
    conflicting = StockMovement(
        id=movement.pk,
        variant=movement.variant,
        delta=4,
        reason=MovementReason.RESTOCK,
    )

    with pytest.raises(TypeError):
        StockMovement.objects.bulk_create(
            [conflicting],
            update_conflicts=True,
            update_fields=["delta"],
            unique_fields=["id"],
        )

    movement.refresh_from_db()
    assert movement.delta == 3


def test_positional_stock_movement_conflict_upsert_is_rejected():
    """Positional conflict flags cannot bypass append-only ledger protection."""
    movement = StockMovement.objects.create(
        variant=_create_variant(),
        delta=3,
        reason=MovementReason.RESTOCK,
    )
    conflicting = StockMovement(
        id=movement.pk,
        variant=movement.variant,
        delta=4,
        reason=MovementReason.RESTOCK,
    )

    with pytest.raises(TypeError):
        StockMovement.objects.bulk_create(
            [conflicting],
            None,  # batch_size
            False,  # ignore_conflicts
            True,  # update_conflicts
            ["delta"],  # update_fields
            ["id"],  # unique_fields
        )

    movement.refresh_from_db()
    assert movement.delta == 3


def test_seed_demo_is_idempotent_and_preserves_live_inventory():
    """Rerunning seed_demo must fill the matrix once without resetting operational stock."""
    first_output = StringIO()
    call_command("seed_demo", stdout=first_output)

    # Five products each receive 6 sizes x 2 colors x 3 fits = 36 variants.
    assert Category.objects.count() == 5
    assert Product.objects.count() == 5
    assert ProductVariant.objects.count() == 180
    assert StockRecord.objects.count() == 180
    assert StockMovement.objects.count() == 180

    stock = StockRecord.objects.order_by("pk").first()
    assert stock is not None
    # Simulate a live adjustment with the same lock + ledger pairing B-1 will
    # encapsulate. This keeps the test itself faithful to the stock invariants.
    with transaction.atomic():
        stock = StockRecord.objects.select_for_update().get(pk=stock.pk)
        stock.qty_on_hand = 7
        stock.qty_reserved = 2
        stock.low_stock_threshold = 3
        stock.save(update_fields=["qty_on_hand", "qty_reserved", "low_stock_threshold"])
        StockMovement.objects.create(
            variant=stock.variant,
            delta=-3,
            reason=MovementReason.ADJUSTMENT,
        )

    second_output = StringIO()
    call_command("seed_demo", stdout=second_output)

    # No catalog, stock, or ledger duplicates may appear on the second invocation.
    assert Category.objects.count() == 5
    assert Product.objects.count() == 5
    assert ProductVariant.objects.count() == 180
    assert StockRecord.objects.count() == 180
    assert StockMovement.objects.count() == 181

    stock.refresh_from_db()
    assert stock.qty_on_hand == 7
    assert stock.qty_reserved == 2
    assert stock.low_stock_threshold == 3
