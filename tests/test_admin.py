"""Admin registration and variant-matrix generator tests (C-1).

Verifies that all model admin registrations load without errors and that
the variant-matrix generator creates the correct number of variants.
"""

import pytest
from unittest.mock import patch
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

    def test_generates_full_matrix_for_one_color(self, mock_message_user, product, request_factory, admin_site):
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

    def test_generates_full_matrix_for_two_colors(self, mock_message_user, product, request_factory, admin_site):
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

    def test_idempotent_matrix_generation(self, mock_message_user, product, request_factory, admin_site):
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

    def test_generates_default_color_when_no_variants(self, mock_message_user, product, request_factory, admin_site):
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
