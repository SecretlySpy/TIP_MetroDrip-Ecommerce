"""Safety and content contracts for the temporary M1 seed browser."""

from io import StringIO

import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings

from apps.catalog.management.commands.seed_demo import PRODUCT_SEEDS
from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.orders.money import format_centavos


def test_staging_seed_preview_is_disabled_by_default():
    """Development and production inherit a closed gate unless staging opts in."""
    assert settings.STAGING_SEED_PREVIEW_ENABLED is False


@override_settings(STAGING_SEED_PREVIEW_ENABLED=False)
def test_staging_seed_preview_returns_not_found_when_disabled(client):
    """A 404 avoids advertising the temporary operational page outside staging."""
    response = client.get("/staging/seed/")

    assert response.status_code == 404


@override_settings(STAGING_SEED_PREVIEW_ENABLED=False)
def test_staging_seed_preview_hides_non_get_methods_when_disabled(client):
    """A closed gate must not reveal that the temporary route accepts only GET."""
    response = client.post("/staging/seed/", data={"is_active": False})

    assert response.status_code == 404


@override_settings(STAGING_SEED_PREVIEW_ENABLED=True)
def test_staging_seed_preview_rejects_post_requests(client):
    """The seed browser is observability-only and must expose no mutation surface."""
    response = client.post("/staging/seed/", data={"is_active": False})

    assert response.status_code == 405
    assert response.headers["Allow"] == "GET"


@pytest.mark.django_db
@override_settings(STAGING_SEED_PREVIEW_ENABLED=True)
def test_staging_seed_preview_lists_only_the_complete_active_seed(client):
    """The M1 page must visibly prove five products and their 180-SKU matrix exist."""
    # Suppressing command output keeps test logs focused on assertion failures.
    call_command("seed_demo", stdout=StringIO())

    # An inactive product with a real variant proves both list and aggregate
    # queries apply the active-product boundary rather than passing by accident.
    category = Category.objects.order_by("pk").first()
    assert category is not None
    inactive_product = Product.objects.create(
        name="Hidden staging sentinel",
        slug="hidden-staging-sentinel",
        description="This inactive product must never appear in the staging browser.",
        category=category,
        base_price=12_345,
        images=[],
        is_active=False,
    )
    ProductVariant.objects.create(
        product=inactive_product,
        sku="MD-HIDDEN-M-BLACK-REG",
        size=Size.M,
        color="Hidden Black",
        fit=Fit.REGULAR,
    )

    response = client.get("/staging/seed/")

    assert response.status_code == 200
    assert any(template.name == "staging/seed_preview.html" for template in response.templates)

    products = list(response.context["products"])
    products_by_name = {product.name: product for product in products}
    expected_names = {seed["name"] for seed in PRODUCT_SEEDS}

    assert response.context["product_count"] == 5
    assert response.context["total_variants"] == 180
    assert len(products) == 5
    assert set(products_by_name) == expected_names
    assert all(product.is_active for product in products)
    assert all(product.variant_count == 36 for product in products)
    assert sum(product.variant_count for product in products) == 180

    rendered_page = response.content.decode("utf-8")
    for seed in PRODUCT_SEEDS:
        # Each card must expose identity, category, and a shared-helper peso price.
        assert seed["name"] in rendered_page
        assert seed["category_name"] in rendered_page
        assert format_centavos(seed["base_price"]) in rendered_page

    assert "5 products / 180 variants" in rendered_page
    assert inactive_product.name not in rendered_page
