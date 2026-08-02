"""FR-27 — push fan-out on Paid / Shipped / Out for Delivery / Delivered."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.accounts.models import Customer
from apps.catalog.models import Category, Product, ProductVariant
from apps.notifications.models import DeviceToken, Notification
from apps.orders.models import Order, OrderStatus
from apps.shipping.models import Shipment, ShipmentStatus


@pytest.fixture
def shopper(db):
    user = Customer.objects.create_user(email="push@example.com", password="x" * 12)
    DeviceToken.objects.create(customer=user, token="ExponentPushToken[test]", platform="android")
    return user


def _order_for(shopper):
    category = Category.objects.create(name="Tees", slug="tees-push")
    product = Product.objects.create(
        name="Push Tee", slug="push-tee", category=category, base_price=10000
    )
    ProductVariant.objects.create(
        product=product, sku="PUSH-TEE-M", size="M", color="Black", fit="regular"
    )
    return Order.objects.create(
        order_no="MD-2026-PUSH1",
        customer=shopper,
        subtotal=10000,
        shipping_fee=9900,
        total=19900,
        shipping_address={"email": shopper.email, "name": "Push", "phone": "", "city": "Manila"},
    )


@pytest.mark.django_db(transaction=True)
def test_paid_creates_notification(shopper):
    order = _order_for(shopper)
    order.transition_to(OrderStatus.PAID)
    assert Notification.objects.filter(customer=shopper, order=order).count() >= 1


@pytest.mark.django_db(transaction=True)
def test_shipped_and_delivered_notify(shopper):
    order = _order_for(shopper)
    order.transition_to(OrderStatus.PAID)
    order.transition_to(OrderStatus.PACKED)
    order.transition_to(OrderStatus.SHIPPED)
    titles = list(
        Notification.objects.filter(customer=shopper, order=order).values_list("title", flat=True)
    )
    assert any("way" in t.lower() or "ship" in t.lower() for t in titles)

    order.transition_to(OrderStatus.DELIVERED)
    titles = list(
        Notification.objects.filter(customer=shopper, order=order).values_list("title", flat=True)
    )
    assert any("deliver" in t.lower() for t in titles)


@pytest.mark.django_db(transaction=True)
def test_out_for_delivery_shipment_edge_notifies(shopper):
    order = _order_for(shopper)
    order.transition_to(OrderStatus.PAID)
    order.transition_to(OrderStatus.PACKED)
    order.transition_to(OrderStatus.SHIPPED)
    before = Notification.objects.filter(customer=shopper).count()
    shipment = Shipment.objects.create(order=order, courier="jnt", waybill_no="JNT1")
    shipment.status = ShipmentStatus.OUT_FOR_DELIVERY
    shipment.save()
    after = Notification.objects.filter(customer=shopper).count()
    assert after == before + 1
    latest = Notification.objects.filter(customer=shopper).latest("id")
    assert "delivery" in latest.title.lower() or "delivery" in latest.body.lower()


@pytest.mark.django_db(transaction=True)
def test_guest_orders_skip_push(db):
    category = Category.objects.create(name="G", slug="g-guest")
    product = Product.objects.create(name="G", slug="g-guest", category=category, base_price=1000)
    ProductVariant.objects.create(
        product=product, sku="G-1", size="M", color="Black", fit="regular"
    )
    order = Order.objects.create(
        order_no="MD-2026-GUEST",
        customer=None,
        subtotal=1000,
        shipping_fee=0,
        total=1000,
        shipping_address={"email": "g@example.com"},
    )
    with patch("apps.notifications.push.send_push") as send_push:
        order.transition_to(OrderStatus.PAID)
        send_push.assert_not_called()
    assert Notification.objects.count() == 0
