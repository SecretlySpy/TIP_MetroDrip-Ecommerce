"""Storefront views tests (C-2/C-3/C-4).

Tests for the homepage, shop listing (filters, search, sort), product detail
(with variant data), cart page, and availability endpoint.
"""

import json

import pytest
from django.test import Client

from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import StockRecord

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def category():
    return Category.objects.create(name="T-Shirts", slug="t-shirts")


@pytest.fixture()
def category2():
    return Category.objects.create(name="Hoodies", slug="hoodies")


@pytest.fixture()
def product(category):
    return Product.objects.create(
        name="Metro Essential Tee",
        slug="metro-essential-tee",
        category=category,
        base_price=89900,
        description="A premium essential tee for the urban commuter.",
    )


@pytest.fixture()
def product2(category2):
    return Product.objects.create(
        name="Skyline Hoodie",
        slug="skyline-hoodie",
        category=category2,
        base_price=189900,
        description="A pullover hoodie built for the skyline.",
    )


@pytest.fixture()
def variant(product):
    v = ProductVariant.objects.create(
        product=product, sku="MD-MTEE-M-JBLK-REG",
        size=Size.M, color="Jet Black", fit=Fit.REGULAR,
    )
    StockRecord.objects.create(variant=v, qty_on_hand=10, qty_reserved=0, low_stock_threshold=5)
    return v


@pytest.fixture()
def variant_out_of_stock(product):
    v = ProductVariant.objects.create(
        product=product, sku="MD-MTEE-L-CWHT-SLM",
        size=Size.L, color="Concrete White", fit=Fit.SLIM,
    )
    StockRecord.objects.create(variant=v, qty_on_hand=0, qty_reserved=0, low_stock_threshold=5)
    return v


@pytest.fixture()
def variant2(product2):
    v = ProductVariant.objects.create(
        product=product2, sku="MD-SHOD-S-MNAV-OVR",
        size=Size.S, color="Midnight Navy", fit=Fit.OVERSIZED,
    )
    StockRecord.objects.create(variant=v, qty_on_hand=5, qty_reserved=0, low_stock_threshold=5)
    return v


@pytest.fixture()
def client():
    return Client()


# ---------------------------------------------------------------------------
# Homepage Tests
# ---------------------------------------------------------------------------

class TestHomepage:
    def test_homepage_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_homepage_contains_brand_name(self, client):
        response = client.get("/")
        assert b"MetroDrip" in response.content

    def test_homepage_shows_featured_products(self, client, product, variant):
        response = client.get("/")
        assert product.name.encode() in response.content


# ---------------------------------------------------------------------------
# Shop Listing Tests
# ---------------------------------------------------------------------------

class TestShopListing:
    def test_shop_returns_200(self, client):
        response = client.get("/shop/")
        assert response.status_code == 200

    def test_shop_shows_active_products(self, client, product, variant):
        response = client.get("/shop/")
        assert product.name.encode() in response.content

    def test_shop_hides_inactive_products(self, client, product, variant):
        product.is_active = False
        product.save(update_fields=["is_active"])
        response = client.get("/shop/")
        assert product.name.encode() not in response.content

    def test_filter_by_category(self, client, product, variant, product2, variant2):
        response = client.get("/shop/?category=t-shirts")
        assert product.name.encode() in response.content
        assert product2.name.encode() not in response.content

    def test_filter_by_size(self, client, product, variant, variant2):
        response = client.get("/shop/?size=M")
        assert product.name.encode() in response.content

    def test_filter_by_fit(self, client, product, variant, product2, variant2):
        response = client.get("/shop/?fit=regular")
        assert product.name.encode() in response.content

    def test_search_by_name(self, client, product, variant, product2, variant2):
        response = client.get("/shop/?q=Essential")
        assert product.name.encode() in response.content
        assert product2.name.encode() not in response.content

    def test_search_by_sku(self, client, product, variant):
        response = client.get("/shop/?q=MTEE")
        assert product.name.encode() in response.content

    def test_sort_by_price_asc(self, client, product, variant, product2, variant2):
        response = client.get("/shop/?sort=price_asc")
        assert response.status_code == 200
        content = response.content.decode()
        # The cheaper product should appear before the expensive one.
        pos_tee = content.find(product.name)
        pos_hoodie = content.find(product2.name)
        assert pos_tee < pos_hoodie

    def test_sort_by_price_desc(self, client, product, variant, product2, variant2):
        response = client.get("/shop/?sort=price_desc")
        assert response.status_code == 200
        content = response.content.decode()
        pos_tee = content.find(product.name)
        pos_hoodie = content.find(product2.name)
        assert pos_hoodie < pos_tee

    def test_sort_by_newest(self, client, product, variant, product2, variant2):
        response = client.get("/shop/?sort=newest")
        assert response.status_code == 200

    def test_sort_by_name(self, client, product, variant, product2, variant2):
        response = client.get("/shop/?sort=name_asc")
        assert response.status_code == 200

    def test_empty_search_returns_all(self, client, product, variant, product2, variant2):
        response = client.get("/shop/?q=")
        assert response.status_code == 200
        assert product.name.encode() in response.content
        assert product2.name.encode() in response.content

    def test_htmx_request_returns_partial(self, client, product, variant):
        """HTMX requests should get just the product grid fragment."""
        response = client.get("/shop/", HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        # The partial should NOT contain the full page chrome (navbar).
        assert b"navbar" not in response.content
        # But should contain product data.
        assert product.name.encode() in response.content


# ---------------------------------------------------------------------------
# Product Detail Tests
# ---------------------------------------------------------------------------

class TestProductDetail:
    def test_detail_returns_200(self, client, product, variant):
        response = client.get(f"/shop/{product.slug}/")
        assert response.status_code == 200

    def test_detail_404_for_invalid_slug(self, client):
        response = client.get("/shop/does-not-exist/")
        assert response.status_code == 404

    def test_detail_404_for_inactive_product(self, client, product, variant):
        product.is_active = False
        product.save(update_fields=["is_active"])
        response = client.get(f"/shop/{product.slug}/")
        assert response.status_code == 404

    def test_detail_contains_product_name(self, client, product, variant):
        response = client.get(f"/shop/{product.slug}/")
        assert product.name.encode() in response.content

    def test_detail_contains_variant_json(self, client, product, variant):
        """The variant picker needs JSON-serialized variant data."""
        response = client.get(f"/shop/{product.slug}/")
        content = response.content.decode()
        assert variant.sku in content
        assert '"available": 10' in content  # from the StockRecord fixture

    def test_detail_shows_out_of_stock_variant(
        self, client, product, variant, variant_out_of_stock,
    ):
        """Out-of-stock variants are included with available=0."""
        response = client.get(f"/shop/{product.slug}/")
        content = response.content.decode()
        assert variant_out_of_stock.sku in content
        assert '"available": 0' in content

    def test_detail_shows_category(self, client, product, variant):
        response = client.get(f"/shop/{product.slug}/")
        assert product.category.name.encode() in response.content


# ---------------------------------------------------------------------------
# Cart Page Tests
# ---------------------------------------------------------------------------

class TestCartPage:
    def test_cart_page_returns_200(self, client):
        response = client.get("/cart/")
        assert response.status_code == 200

    def test_cart_page_contains_cart_js(self, client):
        """The cart page must load the cart.js module."""
        response = client.get("/cart/")
        assert b"cart.js" in response.content


# ---------------------------------------------------------------------------
# Cart Availability Endpoint Tests
# ---------------------------------------------------------------------------

class TestCartAvailability:
    def test_availability_returns_stock(self, client, variant):
        response = client.get(f"/api/cart/availability/?ids={variant.id}")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["availability"][str(variant.id)] == 10

    def test_availability_returns_zero_for_unknown_variant(self, client):
        response = client.get("/api/cart/availability/?ids=99999")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["availability"]["99999"] == 0

    def test_availability_multiple_ids(self, client, variant, variant_out_of_stock):
        response = client.get(
            f"/api/cart/availability/?ids={variant.id},{variant_out_of_stock.id}"
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["availability"][str(variant.id)] == 10
        assert data["availability"][str(variant_out_of_stock.id)] == 0

    def test_availability_rejects_invalid_ids(self, client):
        response = client.get("/api/cart/availability/?ids=abc")
        assert response.status_code == 400

    def test_availability_rejects_empty_ids(self, client):
        response = client.get("/api/cart/availability/?ids=")
        assert response.status_code == 400

    def test_availability_post_with_json(self, client, variant):
        response = client.post(
            "/api/cart/availability/",
            data=json.dumps({"ids": [variant.id]}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["availability"][str(variant.id)] == 10

    def test_availability_rejects_put(self, client):
        response = client.put("/api/cart/availability/")
        assert response.status_code == 405
