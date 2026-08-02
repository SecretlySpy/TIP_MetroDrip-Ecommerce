"""Contracts for the courier webhook (§7) and the FR-19 printable documents."""

import hashlib
import hmac
import json

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.accounts.models import Customer
from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import StockRecord
from apps.orders.models import Order, OrderItem, OrderStatus
from apps.shipping.models import Shipment, ShipmentStatus

COURIER_SECRET = "courier-test-secret"


def _order_with_item(order_no="MD-2026-70001", qty=3, unit_price=89900):
    category, _ = Category.objects.get_or_create(name="Docs", slug="docs")
    product, _ = Product.objects.get_or_create(
        name="Docs Product",
        slug="docs-product",
        defaults={"category": category, "base_price": unit_price},
    )
    variant = ProductVariant.objects.create(
        product=product,
        sku=f"MD-DOCS-{order_no[-5:]}",
        size=Size.M,
        color=f"Black-{order_no}",
        fit=Fit.REGULAR,
    )
    StockRecord.objects.create(variant=variant, qty_on_hand=20, qty_reserved=0)
    subtotal = unit_price * qty
    order = Order.objects.create(
        order_no=order_no,
        subtotal=subtotal,
        shipping_fee=9900,
        total=subtotal + 9900,
        shipping_address={
            "name": "Doc Buyer",
            "email": "doc@example.com",
            "phone": "09171234567",
            "address_line1": "1 Print St",
            "city": "Quezon City",
            "zone": "NCR",
        },
    )
    OrderItem.objects.create(order=order, variant=variant, qty=qty, unit_price_snapshot=unit_price)
    return order


def _sign(body: bytes, secret=COURIER_SECRET):
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post_courier(client, payload, secret=COURIER_SECRET, sign=True):
    body = json.dumps(payload).encode()
    headers = {"x-courier-signature": _sign(body, secret)} if sign else {}
    return client.post(
        reverse("shipping:courier-webhook"),
        body,
        content_type="application/json",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Courier webhook (§7)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(COURIER_WEBHOOK_SECRET=COURIER_SECRET)
def test_courier_webhook_advances_shipment_and_order(client):
    order = _order_with_item("MD-2026-70001")
    order.transition_to(OrderStatus.PAID)
    order.transition_to(OrderStatus.PACKED)
    order.transition_to(OrderStatus.SHIPPED)
    shipment = Shipment.objects.create(
        order=order, courier="jnt", waybill_no="JT-TEST-0001", status=ShipmentStatus.IN_TRANSIT
    )

    out = _post_courier(client, {"waybill_no": "JT-TEST-0001", "status": "out_for_delivery"})
    assert out.status_code == 200
    shipment.refresh_from_db()
    assert shipment.status == ShipmentStatus.OUT_FOR_DELIVERY

    delivered = _post_courier(client, {"waybill_no": "JT-TEST-0001", "status": "delivered"})
    assert delivered.status_code == 200
    shipment.refresh_from_db()
    order.refresh_from_db()
    assert shipment.status == ShipmentStatus.DELIVERED
    # Delivered is the one carrier state with an order-level counterpart.
    assert order.status == OrderStatus.DELIVERED


@pytest.mark.django_db
@override_settings(COURIER_WEBHOOK_SECRET=COURIER_SECRET)
def test_courier_webhook_is_idempotent(client):
    order = _order_with_item("MD-2026-70002")
    order.transition_to(OrderStatus.PAID)
    order.transition_to(OrderStatus.PACKED)
    order.transition_to(OrderStatus.SHIPPED)
    Shipment.objects.create(
        order=order, courier="jnt", waybill_no="JT-TEST-0002", status=ShipmentStatus.IN_TRANSIT
    )

    first = _post_courier(client, {"waybill_no": "JT-TEST-0002", "status": "delivered"})
    second = _post_courier(client, {"waybill_no": "JT-TEST-0002", "status": "delivered"})

    assert first.status_code == 200
    assert second.status_code == 200  # replay is a no-op, not an error
    order.refresh_from_db()
    assert order.status == OrderStatus.DELIVERED


@pytest.mark.django_db
@override_settings(COURIER_WEBHOOK_SECRET=COURIER_SECRET)
def test_courier_webhook_rejects_bad_signature(client):
    order = _order_with_item("MD-2026-70003")
    Shipment.objects.create(
        order=order, courier="jnt", waybill_no="JT-TEST-0003", status=ShipmentStatus.BOOKED
    )

    unsigned = _post_courier(
        client, {"waybill_no": "JT-TEST-0003", "status": "delivered"}, sign=False
    )
    wrong = _post_courier(
        client, {"waybill_no": "JT-TEST-0003", "status": "delivered"}, secret="wrong-secret"
    )

    assert unsigned.status_code == 400
    assert wrong.status_code == 400
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING  # unauthenticated events change nothing


@pytest.mark.django_db
@override_settings(COURIER_WEBHOOK_SECRET="")
def test_courier_webhook_fails_closed_without_secret(client):
    order = _order_with_item("MD-2026-70004")
    Shipment.objects.create(
        order=order, courier="jnt", waybill_no="JT-TEST-0004", status=ShipmentStatus.BOOKED
    )
    response = _post_courier(
        client, {"waybill_no": "JT-TEST-0004", "status": "delivered"}, secret="anything"
    )
    assert response.status_code == 400


@pytest.mark.django_db
@override_settings(COURIER_WEBHOOK_SECRET=COURIER_SECRET)
def test_courier_webhook_acknowledges_unknown_waybill_and_status(client):
    unknown_waybill = _post_courier(client, {"waybill_no": "NOPE-0000", "status": "delivered"})
    # Acknowledged so the carrier stops retrying; logged for reconciliation.
    assert unknown_waybill.status_code == 200

    order = _order_with_item("MD-2026-70005")
    Shipment.objects.create(
        order=order, courier="jnt", waybill_no="JT-TEST-0005", status=ShipmentStatus.BOOKED
    )
    unmapped = _post_courier(client, {"waybill_no": "JT-TEST-0005", "status": "held_at_customs"})
    assert unmapped.status_code == 200
    assert Shipment.objects.get(waybill_no="JT-TEST-0005").status == ShipmentStatus.BOOKED


# ---------------------------------------------------------------------------
# FR-19: printable documents
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_order_item_line_total_is_exact_centavos():
    order = _order_with_item("MD-2026-70010", qty=3, unit_price=89950)
    item = order.items.get()
    # 899.50 × 3 = 2698.50 — the old widthratio template rounded this to 2697.
    assert item.line_total == 269850


@pytest.mark.django_db
def test_customer_invoice_renders_exact_line_totals(client):
    from django.core.signing import Signer

    order = _order_with_item("MD-2026-70011", qty=3, unit_price=89950)
    token = Signer().sign(str(order.pk))

    response = client.get(reverse("storefront:order-invoice", args=[token]))

    assert response.status_code == 200
    content = response.content.decode()
    assert order.order_no in content
    assert "₱2,698.50" in content  # exact line total, not a rounded peso figure
    assert "₱2,797.50" in content  # subtotal + ₱99 shipping


@pytest.mark.django_db
def test_customer_invoice_requires_valid_token(client):
    assert client.get(reverse("storefront:order-invoice", args=["bogus-token"])).status_code == 404


@pytest.mark.django_db
def test_packing_slip_lists_items_without_prices(client):
    staff = Customer.objects.create_superuser(
        email="packer@example.com", password="Pack!Pass99", name="Packer"
    )
    order = _order_with_item("MD-2026-70012", qty=2, unit_price=89900)
    Shipment.objects.create(
        order=order, courier="jnt", waybill_no="JT-SLIP-0001", status=ShipmentStatus.BOOKED
    )
    client.force_login(staff)

    response = client.get(f"/merchant/orders/order/{order.pk}/packing-slip/")

    assert response.status_code == 200
    content = response.content.decode()
    assert order.items.get().variant.sku in content
    assert "JT-SLIP-0001" in content
    # A packing slip is a pick list — money belongs on the invoice.
    assert "₱899.00" not in content
    assert "₱1,798.00" not in content
