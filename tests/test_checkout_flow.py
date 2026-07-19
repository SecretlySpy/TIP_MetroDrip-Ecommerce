"""End-to-end contracts for checkout (D-1/D-2), mock confirmation, and the
signature-verified PayMongo webhook (D-3, Hard Invariant 3)."""

import hashlib
import hmac
import json

import pytest
from django.core import mail
from django.core.signing import Signer
from django.test import override_settings
from django.urls import reverse

from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import (
    MovementReason,
    Reservation,
    ReservationStatus,
    StockMovement,
    StockRecord,
)
from apps.orders.models import Order, OrderStatus
from apps.payments.models import Payment, PaymentStatus
from apps.shipping.models import ShippingZone

WEBHOOK_SECRET = "test-webhook-secret"


def _make_variant(*, sku="CHK-SKU", base_price=100_00, price_override=None, on_hand=10):
    category, _ = Category.objects.get_or_create(name="Checkout", slug="checkout")
    product, _ = Product.objects.get_or_create(
        name="Checkout Product",
        slug="checkout-product",
        defaults={"category": category, "base_price": base_price},
    )
    variant = ProductVariant.objects.create(
        product=product,
        sku=sku,
        size=Size.M,
        color=f"Black-{sku}",
        fit=Fit.REGULAR,
        price_override=price_override,
    )
    StockRecord.objects.create(variant=variant, qty_on_hand=on_hand, qty_reserved=0)
    return variant


def _make_zone(name="NCR", fee=99_00):
    zone, _ = ShippingZone.objects.get_or_create(name=name, defaults={"fee": fee})
    return zone


def _post_checkout(client, variant, zone, qty=2):
    payload = {
        "customer_name": "Juan dela Cruz",
        "email": "juan@example.com",
        "phone": "09171234567",
        "address_line1": "123 Kalayaan Ave",
        "city": "Quezon City",
        "zone_id": zone.pk,
        "items": [{"variant_id": variant.pk, "qty": qty}],
    }
    return client.post(
        reverse("storefront:checkout"), json.dumps(payload), content_type="application/json"
    )


# ---------------------------------------------------------------------------
# Checkout POST (D-1)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(MOCK_PAYMENTS=True)
def test_checkout_creates_order_holds_and_payment(client):
    # Override price proves checkout charges the effective variant price,
    # never the raw base price.
    variant = _make_variant(base_price=100_00, price_override=120_00)
    zone = _make_zone()

    response = _post_checkout(client, variant, zone, qty=2)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "mock=1" in data["checkout_url"]

    order = Order.objects.get()
    assert order.subtotal == 2 * 120_00
    assert order.shipping_fee == zone.fee
    assert order.total == order.subtotal + zone.fee
    assert order.status == OrderStatus.PENDING
    assert order.shipping_address["email"] == "juan@example.com"

    item = order.items.get()
    assert item.unit_price_snapshot == 120_00

    reservation = order.reservations.get()
    assert reservation.status == ReservationStatus.ACTIVE
    assert reservation.qty == 2

    payment = Payment.objects.get(order=order)
    assert payment.status == PaymentStatus.PENDING
    assert payment.amount == order.total

    stock = StockRecord.objects.get(variant=variant)
    assert (stock.qty_on_hand, stock.qty_reserved) == (10, 2)
    assert StockMovement.objects.count() == 0  # holds are not sales


@pytest.mark.django_db
@override_settings(MOCK_PAYMENTS=True)
def test_checkout_insufficient_stock_rolls_back_everything(client):
    variant = _make_variant(on_hand=1)
    zone = _make_zone()

    response = _post_checkout(client, variant, zone, qty=5)

    assert response.status_code == 409
    # The atomic block must leave no partial order, line, hold, or counter change.
    assert Order.objects.count() == 0
    assert Reservation.objects.count() == 0
    assert Payment.objects.count() == 0
    stock = StockRecord.objects.get(variant=variant)
    assert stock.qty_reserved == 0


@pytest.mark.django_db
@override_settings(MOCK_PAYMENTS=True)
def test_checkout_rejects_bad_payloads(client):
    variant = _make_variant()
    zone = _make_zone()

    url = reverse("storefront:checkout")
    # Empty cart
    body = {"customer_name": "A", "email": "a@b.c", "zone_id": zone.pk, "items": []}
    assert client.post(url, json.dumps(body), content_type="application/json").status_code == 400
    # Unknown zone
    body = {
        "customer_name": "A",
        "email": "a@b.c",
        "zone_id": 99_999,
        "items": [{"variant_id": variant.pk, "qty": 1}],
    }
    assert client.post(url, json.dumps(body), content_type="application/json").status_code == 400
    # Missing contact identity
    body = {"zone_id": zone.pk, "items": [{"variant_id": variant.pk, "qty": 1}]}
    assert client.post(url, json.dumps(body), content_type="application/json").status_code == 400
    assert Order.objects.count() == 0


# ---------------------------------------------------------------------------
# Mock confirmation (development-only sandbox path)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(MOCK_PAYMENTS=True)
def test_mock_success_page_confirms_payment_idempotently(client):
    variant = _make_variant()
    zone = _make_zone()
    checkout_url = _post_checkout(client, variant, zone, qty=2).json()["checkout_url"]

    response = client.get(checkout_url)
    assert response.status_code == 200

    order = Order.objects.get()
    assert order.status == OrderStatus.PAID
    payment = Payment.objects.get(order=order)
    assert payment.status == PaymentStatus.PAID

    stock = StockRecord.objects.get(variant=variant)
    assert (stock.qty_on_hand, stock.qty_reserved) == (8, 0)
    movement = StockMovement.objects.get()
    assert (movement.delta, movement.reason) == (-2, MovementReason.SALE)
    assert movement.ref_order == order
    assert order.reservations.get().status == ReservationStatus.COMMITTED

    # FR-11: confirmation email with the tokenized tracking link.
    assert len(mail.outbox) == 1
    assert order.order_no in mail.outbox[0].subject

    # Replaying the success URL must not double-decrement or resend email.
    client.get(checkout_url)
    stock.refresh_from_db()
    assert stock.qty_on_hand == 8
    assert StockMovement.objects.count() == 1
    assert len(mail.outbox) == 1


@pytest.mark.django_db
@override_settings(MOCK_PAYMENTS=False)
def test_success_page_never_confirms_when_mock_disabled(client):
    variant = _make_variant()
    zone = _make_zone()
    with override_settings(MOCK_PAYMENTS=True):
        checkout_url = _post_checkout(client, variant, zone).json()["checkout_url"]

    client.get(checkout_url)  # mock=1 present, but the gate is off

    assert Order.objects.get().status == OrderStatus.PENDING
    assert Payment.objects.get().status == PaymentStatus.PENDING


@pytest.mark.django_db
def test_checkout_success_requires_valid_token(client):
    assert client.get("/checkout/success/not-a-valid-token/").status_code == 404


# ---------------------------------------------------------------------------
# PayMongo webhook (D-3, Invariant 3)
# ---------------------------------------------------------------------------


def _webhook_body(order_no, method="gcash"):
    return json.dumps(
        {
            "data": {
                "attributes": {
                    "type": "payment.paid",
                    "data": {
                        "attributes": {
                            "reference_number": order_no,
                            "source": {"type": method},
                        }
                    },
                }
            }
        }
    ).encode()


def _signature_for(body, timestamp="1700000000", secret=WEBHOOK_SECRET):
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},te={digest}"


def _paid_order(client, variant, zone):
    with override_settings(MOCK_PAYMENTS=True):
        _post_checkout(client, variant, zone, qty=1)
    return Order.objects.latest("created_at")


@pytest.mark.django_db
@override_settings(PAYMONGO_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_webhook_with_valid_signature_confirms_order(client):
    variant = _make_variant()
    order = _paid_order(client, variant, _make_zone())
    body = _webhook_body(order.order_no)

    response = client.post(
        reverse("payments:paymongo-webhook"),
        body,
        content_type="application/json",
        headers={"paymongo-signature": _signature_for(body)},
    )

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID
    payment = Payment.objects.get(order=order)
    assert payment.status == PaymentStatus.PAID
    assert payment.method == "gcash"  # reported by the webhook, mapped from provider
    stock = StockRecord.objects.get(variant=variant)
    assert (stock.qty_on_hand, stock.qty_reserved) == (9, 0)


@pytest.mark.django_db
@override_settings(PAYMONGO_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_webhook_rejects_bad_or_missing_signature(client):
    variant = _make_variant()
    order = _paid_order(client, variant, _make_zone())
    body = _webhook_body(order.order_no)
    url = reverse("payments:paymongo-webhook")

    no_sig = client.post(url, body, content_type="application/json")
    bad_sig = client.post(
        url,
        body,
        content_type="application/json",
        headers={"paymongo-signature": "t=1700000000,te=deadbeef"},
    )

    assert no_sig.status_code == 400
    assert bad_sig.status_code == 400
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING  # unsigned events never confirm


@pytest.mark.django_db
@override_settings(PAYMONGO_WEBHOOK_SECRET="")
def test_webhook_fails_closed_without_configured_secret(client):
    variant = _make_variant()
    order = _paid_order(client, variant, _make_zone())
    body = _webhook_body(order.order_no)

    response = client.post(
        reverse("payments:paymongo-webhook"),
        body,
        content_type="application/json",
        headers={"paymongo-signature": _signature_for(body, secret="anything")},
    )

    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING


@pytest.mark.django_db
@override_settings(PAYMONGO_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_webhook_replay_is_idempotent(client):
    variant = _make_variant()
    order = _paid_order(client, variant, _make_zone())
    body = _webhook_body(order.order_no)
    url = reverse("payments:paymongo-webhook")
    headers = {"paymongo-signature": _signature_for(body)}

    first = client.post(url, body, content_type="application/json", headers=headers)
    second = client.post(url, body, content_type="application/json", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    stock = StockRecord.objects.get(variant=variant)
    assert stock.qty_on_hand == 9  # decremented exactly once
    assert StockMovement.objects.count() == 1
    assert len(mail.outbox) == 1  # confirmation sent exactly once


@pytest.mark.django_db
@override_settings(PAYMONGO_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_webhook_acknowledges_unknown_order_without_processing(client):
    body = _webhook_body("MD-2099-99999")
    response = client.post(
        reverse("payments:paymongo-webhook"),
        body,
        content_type="application/json",
        headers={"paymongo-signature": _signature_for(body)},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tokenized pages (D-4)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(MOCK_PAYMENTS=True)
def test_order_status_page_renders_via_token(client):
    variant = _make_variant()
    order = _paid_order(client, variant, _make_zone())
    token = Signer().sign(str(order.pk))

    response = client.get(reverse("storefront:order-status", args=[token]))

    assert response.status_code == 200
    content = response.content.decode()
    assert order.order_no in content
    assert "Order Status" in content
    # The raw sequential order number must not be a valid status URL.
    assert client.get(f"/order/{order.order_no}/").status_code == 404
