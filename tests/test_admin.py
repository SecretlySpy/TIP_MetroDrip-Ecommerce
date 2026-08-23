"""Admin registration and variant-matrix generator tests (C-1).

Verifies that all model admin registrations load without errors and that
the variant-matrix generator creates the correct number of variants.
"""

from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from apps.catalog.admin import ProductAdmin
from apps.catalog.models import Category, Fit, Product, ProductVariant, Size

pytestmark = pytest.mark.django_db


@pytest.fixture()
def admin_site():
    return AdminSite()


@pytest.fixture()
def request_factory():
    return RequestFactory()


@pytest.fixture()
def category():
    return Category.objects.create(name="Test Category", slug="test-category")


@pytest.fixture()
def product(category):
    return Product.objects.create(
        name="Test Product",
        slug="test-product",
        category=category,
        base_price=100_00,
    )


# ---------------------------------------------------------------------------
# Admin registration smoke tests
# ---------------------------------------------------------------------------


class TestAdminRegistrations:
    """Verify all admin registrations load without import/configuration errors."""

    def test_catalog_admin_loads(self):
        """Catalog admin (Category, Product) can be imported and registered."""
        from apps.catalog import admin as _  # noqa: F401

    def test_inventory_admin_loads(self):
        """Inventory admin (StockRecord, StockMovement, Reservation) loads."""
        from apps.inventory import admin as _  # noqa: F401

    def test_orders_admin_loads(self):
        """Orders admin (Order, OrderItem) loads."""
        from apps.orders import admin as _  # noqa: F401

    def test_payments_admin_loads(self):
        """Payments admin (Payment) loads."""
        from apps.payments import admin as _  # noqa: F401

    def test_shipping_admin_loads(self):
        """Shipping admin (Shipment) loads."""
        from apps.shipping import admin as _  # noqa: F401

    def test_accounts_admin_loads(self):
        """Accounts admin (Customer, WishlistItem) loads."""
        from apps.accounts import admin as _  # noqa: F401

    def test_reviews_admin_loads(self):
        """Reviews admin (Review) loads."""
        from apps.reviews import admin as _  # noqa: F401

    def test_admin_site_accessible(self, client):
        """The /admin/ login page returns 200 (redirect to login)."""
        response = client.get("/admin/login/")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Variant-matrix generator
# ---------------------------------------------------------------------------


@patch("django.contrib.admin.ModelAdmin.message_user")
class TestVariantMatrixGenerator:
    """Test the admin action that generates all Size × Color × Fit variants."""

    def test_generates_full_matrix_for_one_color(
        self, mock_message_user, product, request_factory, admin_site
    ):
        """With one existing color, generates sizes × 1 × fits = 18 variants."""
        # Create one variant to establish a color.
        ProductVariant.objects.create(
            product=product, sku="MD-SEED-001", size=Size.M, color="Black", fit=Fit.REGULAR
        )

        model_admin = ProductAdmin(Product, admin_site)
        request = request_factory.post("/admin/")
        # Django admin actions need the user attribute.
        from apps.accounts.models import Customer

        request.user = Customer.objects.create_superuser(
            email="admin-matrix@test.local", password="testpass123", name="Admin"
        )

        model_admin.generate_variant_matrix(request, Product.objects.filter(pk=product.pk))

        # 6 sizes × 1 color × 3 fits = 18, plus the 1 original = 18 total
        # (the original shares one axes combination with the generated set).
        total = product.variants.count()
        assert total == 18  # 6 × 1 × 3

    def test_generates_full_matrix_for_two_colors(
        self, mock_message_user, product, request_factory, admin_site
    ):
        """With two existing colors, generates sizes × 2 × fits = 36 variants."""
        ProductVariant.objects.create(
            product=product, sku="MD-SEED-002", size=Size.M, color="Black", fit=Fit.REGULAR
        )
        ProductVariant.objects.create(
            product=product, sku="MD-SEED-003", size=Size.M, color="White", fit=Fit.REGULAR
        )

        model_admin = ProductAdmin(Product, admin_site)
        request = request_factory.post("/admin/")
        from apps.accounts.models import Customer

        request.user = Customer.objects.create_superuser(
            email="admin-matrix2@test.local", password="testpass123", name="Admin"
        )

        model_admin.generate_variant_matrix(request, Product.objects.filter(pk=product.pk))

        total = product.variants.count()
        assert total == 36  # 6 × 2 × 3

    def test_idempotent_matrix_generation(
        self, mock_message_user, product, request_factory, admin_site
    ):
        """Running the generator twice doesn't create duplicate variants."""
        ProductVariant.objects.create(
            product=product, sku="MD-SEED-004", size=Size.M, color="Red", fit=Fit.REGULAR
        )

        model_admin = ProductAdmin(Product, admin_site)
        request = request_factory.post("/admin/")
        from apps.accounts.models import Customer

        request.user = Customer.objects.create_superuser(
            email="admin-idem@test.local", password="testpass123", name="Admin"
        )
        queryset = Product.objects.filter(pk=product.pk)

        model_admin.generate_variant_matrix(request, queryset)
        first_count = product.variants.count()

        model_admin.generate_variant_matrix(request, queryset)
        second_count = product.variants.count()

        assert first_count == second_count

    def test_generates_default_color_when_no_variants(
        self, mock_message_user, product, request_factory, admin_site
    ):
        """A product with no existing variants gets a 'Default' color matrix."""
        model_admin = ProductAdmin(Product, admin_site)
        request = request_factory.post("/admin/")
        from apps.accounts.models import Customer

        request.user = Customer.objects.create_superuser(
            email="admin-default@test.local", password="testpass123", name="Admin"
        )

        model_admin.generate_variant_matrix(request, Product.objects.filter(pk=product.pk))

        total = product.variants.count()
        assert total == 18  # 6 × 1 ("Default") × 3
        assert product.variants.filter(color="Default").exists()


# ---------------------------------------------------------------------------
# Refund / cancel atomicity (ADR-P3-027)
# ---------------------------------------------------------------------------


@patch("django.contrib.admin.ModelAdmin.message_user")
class TestRefundAtomicity:
    """A refund that fails mid-loop must leave the order and its stock untouched.

    The action previously transitioned the order first and then restored each
    line in a bare loop, so a failure on line 2 of 3 committed the REFUNDED
    transition and part of the restock. Both assertions below fail against that
    version, which is what makes them a regression test rather than a
    restatement of the implementation.
    """

    @staticmethod
    def _order_with_lines(n_lines, tag="a"):
        """A PAID order with `n_lines` distinct single-unit variants.

        `tag` namespaces every unique key so one test can build several orders.
        """
        from apps.accounts.models import Customer
        from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
        from apps.inventory.models import StockRecord
        from apps.orders.models import Order, OrderItem, OrderStatus

        category = Category.objects.create(name=f"Refund {tag}", slug=f"refund-cat-{tag}")
        product = Product.objects.create(
            name=f"Refund Product {tag}",
            slug=f"refund-product-{tag}",
            category=category,
            base_price=100_00,
        )
        customer = Customer.objects.create_user(
            email=f"refund-buyer-{tag}@test.local", password="testpass123", name="Buyer"
        )
        order = Order.objects.create(
            order_no=f"MD-2026-9{ord(tag) % 10}{n_lines:03d}",
            customer=customer,
            subtotal=100_00 * n_lines,
            shipping_fee=0,
            total=100_00 * n_lines,
            shipping_address={"name": "Buyer", "email": "refund-buyer@test.local"},
        )
        # Invariant 5: orders are born PENDING and only ever move along a legal
        # edge, so PAID has to be reached rather than assigned.
        order.transition_to(OrderStatus.PAID)
        variants = []
        for index in range(n_lines):
            variant = ProductVariant.objects.create(
                product=product,
                sku=f"MD-REF-{tag}-{index:03d}",
                size=Size.M,
                color=f"Color{tag}{index}",
                fit=Fit.REGULAR,
            )
            StockRecord.objects.create(variant=variant, qty_on_hand=0, qty_reserved=0)
            OrderItem.objects.create(
                order=order, variant=variant, qty=1, unit_price_snapshot=100_00
            )
            variants.append(variant)
        return order, variants

    def test_failure_on_line_two_rolls_back_the_whole_refund(
        self, mock_message_user, request_factory, admin_site
    ):
        from apps.accounts.models import Customer
        from apps.inventory.models import StockRecord
        from apps.orders.admin import OrderAdmin
        from apps.orders.models import Order, OrderStatus

        order, variants = self._order_with_lines(3)

        model_admin = OrderAdmin(Order, admin_site)
        request = request_factory.post("/merchant/")
        request.user = Customer.objects.create_superuser(
            email="admin-refund@test.local", password="testpass123", name="Admin"
        )

        # Restore line 1, then fail line 2. The real adjust_stock is used for the
        # first call so there is a committed-looking write for the rollback to
        # actually have to undo — a mock that never writes would pass trivially.
        real_adjust = __import__("apps.inventory.services", fromlist=["adjust_stock"]).adjust_stock
        calls = {"n": 0}

        def flaky_adjust(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("ledger unavailable")
            return real_adjust(**kwargs)

        with patch("apps.inventory.services.adjust_stock", side_effect=flaky_adjust):
            model_admin.mark_as_refunded(request, Order.objects.filter(pk=order.pk))

        order.refresh_from_db()
        assert order.status == OrderStatus.PAID, (
            "order must not stay REFUNDED after a failed restore"
        )

        for variant in variants:
            record = StockRecord.objects.get(variant=variant)
            assert record.qty_on_hand == 0, f"{variant.sku} was restocked despite the rollback"

    def test_one_bad_order_does_not_abort_the_rest_of_the_selection(
        self, mock_message_user, request_factory, admin_site
    ):
        """A ledger fault on order A must still let order B refund.

        Only IllegalTransition was caught before, so any other exception escaped
        the action entirely and every order after the failure was silently
        skipped with a 500.
        """
        from apps.accounts.models import Customer
        from apps.orders.admin import OrderAdmin
        from apps.orders.models import Order, OrderStatus

        bad_order, _ = self._order_with_lines(1, tag="b")
        good_order, _ = self._order_with_lines(1, tag="c")

        model_admin = OrderAdmin(Order, admin_site)
        request = request_factory.post("/merchant/")
        request.user = Customer.objects.create_superuser(
            email="admin-refund2@test.local", password="testpass123", name="Admin"
        )

        real_adjust = __import__("apps.inventory.services", fromlist=["adjust_stock"]).adjust_stock

        def only_bad_order_fails(**kwargs):
            if kwargs.get("ref_order") and kwargs["ref_order"].pk == bad_order.pk:
                raise RuntimeError("ledger unavailable")
            return real_adjust(**kwargs)

        with patch("apps.inventory.services.adjust_stock", side_effect=only_bad_order_fails):
            model_admin.mark_as_refunded(
                request, Order.objects.filter(pk__in=[bad_order.pk, good_order.pk])
            )

        bad_order.refresh_from_db()
        good_order.refresh_from_db()
        assert bad_order.status == OrderStatus.PAID
        assert good_order.status == OrderStatus.REFUNDED, "the healthy order was skipped"
