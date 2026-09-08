"""Executed against five real MySQL schemas; no SQLite substitution."""

import pytest
from django.core.management import call_command
from django.db import IntegrityError, connections, transaction
from django.db.models.deletion import ProtectedError
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import Customer, WishlistItem
from apps.catalog.models import Category, Product, ProductVariant
from apps.inventory.models import StockRecord
from apps.orders.models import Order, OrderItem
from apps.payments.providers.simulated import SimulatedPaymentProvider

pytestmark = pytest.mark.django_db(transaction=True, databases="__all__")


@pytest.fixture
def purchase():
    customer = Customer.objects.create_user(
        email="schema@example.test", name="Buyer", password="test"
    )
    category = Category.objects.create(name="Tops", slug="tops")
    product = Product.objects.create(
        name="Original tee",
        slug="original-tee",
        category=category,
        base_price=12500,
        images=["https://example.test/original.jpg"],
    )
    variant = ProductVariant.objects.create(
        product=product, sku="ORIGINAL-M", size="M", color="Black", fit="regular"
    )
    stock = StockRecord.objects.create(variant=variant, qty_on_hand=10)
    order = Order.objects.create(
        order_no="MD-2026-00001", customer=customer, subtotal=12500, shipping_fee=500, total=13000
    )
    line = OrderItem.objects.create(order=order, variant=variant, qty=1, unit_price_snapshot=12500)
    return customer, product, variant, stock, order, line


def test_physical_schema_contract():
    call_command("validate_service_schemas")


def test_owner_routes_and_real_local_fks(purchase):
    customer, product, variant, stock, order, line = purchase
    assert customer._state.db == "identity"
    assert product._state.db == variant._state.db == stock._state.db == "catalog"
    assert order._state.db == line._state.db == "default"
    with connections["catalog"].cursor() as cursor:
        constraints = connections["catalog"].introspection.get_constraints(
            cursor, stock._meta.db_table
        )
    assert any(
        c.get("foreign_key") == ("catalog_productvariant", "id") for c in constraints.values()
    )


def test_history_is_immutable_and_reads_no_catalog(purchase):
    _, product, variant, _, _, line = purchase
    product.name = "Renamed tee"
    product.slug = "renamed"
    product.save()
    variant.sku = "RENAMED-L"
    variant.size = "L"
    variant.color = "Red"
    variant.fit = "oversized"
    variant.save()
    with CaptureQueriesContext(connections["catalog"]) as queries:
        saved = OrderItem.objects.get(pk=line.pk)
        assert (
            saved.product_name_snapshot,
            saved.sku_snapshot,
            saved.size_snapshot,
            saved.color_snapshot,
            saved.fit_snapshot,
            saved.unit_price_snapshot,
        ) == ("Original tee", "ORIGINAL-M", "M", "Black", "regular", 12500)
        assert saved.get_size_display() == "Medium"
    assert len(queries) == 0
    with pytest.raises(ValueError):
        OrderItem.objects.filter(pk=line.pk).update(sku_snapshot="rewrite")
    saved.product_name_snapshot = "rewrite"
    with pytest.raises(ValueError):
        saved.save()


def test_cross_service_protection_and_cleanup(purchase):
    customer, product, variant, _, order, _ = purchase
    WishlistItem.objects.create(customer=customer, product=product)
    with pytest.raises(ProtectedError):
        variant.delete()
    customer.delete()
    order.refresh_from_db()
    assert order.customer_id is None
    assert not WishlistItem.objects.exists()


def test_invalid_status_rejected_by_database(purchase):
    *_, order, line = purchase
    with pytest.raises(IntegrityError), transaction.atomic():
        with connections["default"].cursor() as cursor:
            cursor.execute("UPDATE orders_order SET status=%s WHERE id=%s", ["invented", order.pk])


def test_payment_rollback_does_not_consume_catalog_stock(purchase):
    import datetime

    from django.utils import timezone

    from apps.inventory.services import reserve_lines
    from apps.orders.models import StockHold

    _, _, variant, stock, order, _ = purchase
    reserve_lines(checkout_id="rollback-hold", lines=[{"variant_id": variant.pk, "qty": 1}])
    StockHold.objects.create(
        order=order,
        checkout_id="rollback-hold",
        expires_at=timezone.now() + datetime.timedelta(minutes=15),
    )
    provider = SimulatedPaymentProvider()
    provider.create_checkout_session(
        order, "https://example.test/success", "https://example.test/cancel"
    )
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            provider.confirm_order_paid(order=order)
            raise RuntimeError("abort payment transaction")
    stock.refresh_from_db()
    assert stock.qty_on_hand == 10
    assert stock.qty_reserved == 1
    order.refresh_from_db()
    assert order.status == "pending"
    assert provider.confirm_order_paid(order=order)
    stock.refresh_from_db()
    assert (stock.qty_on_hand, stock.qty_reserved) == (9, 0)
    assert provider.confirm_order_paid(order=order) is False
    stock.refresh_from_db()
    assert stock.qty_on_hand == 9


def test_purchase_snapshot_cannot_be_rewritten_with_sql(purchase):
    from django.db import DatabaseError

    *_, line = purchase
    with pytest.raises(DatabaseError), transaction.atomic():
        with connections["default"].cursor() as cursor:
            cursor.execute(
                "UPDATE orders_orderitem SET sku_snapshot=%s WHERE id=%s", ["rewritten", line.pk]
            )
    line.refresh_from_db()
    assert line.sku_snapshot != "rewritten"


def test_fulfillment_delivery_replay_never_creates_a_second_sale(purchase):
    from django.utils import timezone

    from apps.inventory.services import reserve_lines
    from apps.orders.models import OrderStatus, StockHold
    from apps.payments.holds import deliver_order_stock

    _, _, variant, stock, order, _ = purchase
    reserve_lines(checkout_id="delivery-replay", lines=[{"variant_id": variant.pk, "qty": 1}])
    StockHold.objects.create(order=order, checkout_id="delivery-replay", expires_at=timezone.now())
    order.transition_to(OrderStatus.PAID)
    deliver_order_stock({"order_id": order.pk})
    deliver_order_stock({"order_id": order.pk})
    stock.refresh_from_db()
    assert stock.qty_on_hand == 9
    assert stock.qty_reserved == 0
    assert variant.movements.filter(reason="sale", ref_order_id=order.pk).count() == 1


def test_refund_before_stock_fulfillment_cannot_invent_stock(purchase):
    from apps.inventory.services import restore_order_stock

    _, _, variant, stock, order, _ = purchase
    restore_order_stock(order=order, lines=[{"variant_id": variant.pk, "qty": 1}])
    restore_order_stock(order=order, lines=[{"variant_id": variant.pk, "qty": 1}])
    stock.refresh_from_db()
    assert stock.qty_on_hand == 10
    assert variant.movements.count() == 0
