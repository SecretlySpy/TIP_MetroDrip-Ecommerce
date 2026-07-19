"""Render smoke tests for every public page.

These exist because pages can 500 on template-layer defects (missing filter
libraries, undefined tags) that no service-level test touches — exactly what
happened with `storefront_tags` and `centavos_to_peso` before this suite.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from apps.accounts.models import Customer
from apps.catalog.models import Product
from apps.cms.models import ContactMessage
from apps.shipping.models import ShippingZone


@pytest.fixture
def seeded(db):
    call_command("seed_demo", stdout=StringIO())


@pytest.fixture
def customer(db):
    return Customer.objects.create_user(
        email="shopper@example.com", password="s3cretpass!", name="Shopper"
    )


def _login(client, customer):
    client.force_login(customer)


def test_homepage_renders(client, seeded):
    response = client.get(reverse("storefront:home"))
    assert response.status_code == 200


def test_shop_listing_renders_with_filters(client, seeded):
    response = client.get(
        reverse("storefront:shop"), {"size": "M", "sort": "price_asc", "q": "tee"}
    )
    assert response.status_code == 200


def test_product_detail_renders(client, seeded):
    product = Product.objects.first()
    response = client.get(reverse("storefront:product-detail", args=[product.slug]))
    assert response.status_code == 200
    assert product.name in response.content.decode()


def test_cart_page_renders(client):
    assert client.get(reverse("storefront:cart")).status_code == 200


def test_checkout_page_renders_with_zones(client, seeded):
    response = client.get(reverse("storefront:checkout"))
    assert response.status_code == 200
    content = response.content.decode()
    for zone in ShippingZone.objects.filter(is_active=True):
        assert zone.name in content
    assert "csrfmiddlewaretoken" in content  # the JSON POST needs the CSRF cookie


@pytest.mark.django_db
def test_contact_page_stores_and_alerts(client):
    assert client.get(reverse("storefront:contact")).status_code == 200

    with override_settings(CONTACT_ALERT_RECIPIENTS=["staff@metrodrip.example"]):
        from django.core import mail

        response = client.post(
            reverse("storefront:contact"),
            {"name": "Ana", "email": "ana@example.com", "message": "Where is my order?"},
        )
        assert response.status_code == 200
        assert ContactMessage.objects.count() == 1
        assert len(mail.outbox) == 1

    # Missing fields re-render with an error instead of storing.
    response = client.post(reverse("storefront:contact"), {"name": "", "email": "", "message": ""})
    assert response.status_code == 200
    assert ContactMessage.objects.count() == 1


def test_flatpages_render(client, seeded):
    for url in ("/pages/about/", "/pages/faq/", "/pages/privacy/"):
        assert client.get(url).status_code == 200, url


def test_login_and_register_pages_render(client):
    assert client.get(reverse("accounts:login")).status_code == 200
    assert client.get(reverse("accounts:register")).status_code == 200


def test_profile_page_renders(client, customer):
    _login(client, customer)
    assert client.get(reverse("accounts:profile")).status_code == 200


def test_profile_update_persists(client, customer):
    _login(client, customer)
    response = client.post(
        reverse("accounts:profile"), {"name": "Renamed Shopper", "phone": "09998887777"}
    )
    assert response.status_code == 302
    customer.refresh_from_db()
    assert customer.name == "Renamed Shopper"
    assert customer.phone == "09998887777"


def test_order_history_renders(client, customer):
    _login(client, customer)
    assert client.get(reverse("accounts:order-history")).status_code == 200


def test_login_next_rejects_external_hosts(client, customer):
    response = client.post(
        reverse("accounts:login") + "?next=https://evil.example/phish",
        {"email": customer.email, "password": "s3cretpass!"},
    )
    # Open-redirect target is discarded in favor of the profile page.
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("accounts:profile")


def test_wishlist_toggle_roundtrip(client, customer, seeded):
    _login(client, customer)
    product = Product.objects.first()

    add = client.post(
        reverse("accounts:toggle-wishlist"),
        f'{{"product_id": {product.pk}}}',
        content_type="application/json",
    )
    remove = client.post(
        reverse("accounts:toggle-wishlist"),
        f'{{"product_id": {product.pk}}}',
        content_type="application/json",
    )

    assert add.json()["added"] is True
    assert remove.json()["added"] is False


def test_cart_availability_endpoint(client, seeded):
    from apps.catalog.models import ProductVariant

    variant = ProductVariant.objects.first()
    response = client.get(reverse("storefront:cart-availability"), {"ids": str(variant.pk)})
    assert response.status_code == 200
    assert response.json()["availability"][str(variant.pk)] == 10
