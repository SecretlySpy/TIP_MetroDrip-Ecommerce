"""Public mobile API contracts (Epic H): auth, catalog, checkout, orders,
wishlist, reviews, notifications — and the M2 no-oversell gate driven through
the API (Milestone M7 QA gate)."""

import json
from queue import Queue
from threading import Barrier, Thread

import pytest
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.models import Customer
from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import Reservation, ReservationStatus, StockRecord
from apps.notifications.models import DeviceToken, Notification
from apps.orders.models import Order, OrderStatus
from apps.payments.models import Payment, PaymentStatus
from apps.shipping.models import ShippingZone

VERSION_HEADERS = {"x-client-version": "1.0.0"}


@pytest.fixture
def api():
    """Client that satisfies the NFR-22 version-header contract."""
    return Client(headers=VERSION_HEADERS)


@pytest.fixture
def customer(db):
    return Customer.objects.create_user(
        email="app@example.com", password="s3cretpass!A9", name="App Shopper", phone="0917"
    )


def _login(api, customer, password="s3cretpass!A9"):
    response = api.post(
        reverse("mobile_api:login"),
        {"email": customer.email, "password": password},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    return response.json()


def _bearer(tokens):
    return {"authorization": f"Bearer {tokens['access']}"}


def _make_variant(*, sku="MOB-SKU", base_price=100_00, price_override=None, on_hand=10):
    category, _ = Category.objects.get_or_create(name="Mobile", slug="mobile")
    product, _ = Product.objects.get_or_create(
        name="Mobile Product",
        slug="mobile-product",
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


def _checkout_payload(variant, zone, qty=1, **overrides):
    payload = {
        "customer_name": "Juan dela Cruz",
        "email": "juan@example.com",
        "phone": "09171234567",
        "address_line1": "123 Kalayaan Ave",
        "city": "Quezon City",
        "zone_id": zone.pk,
        "items": [{"variant_id": variant.pk, "qty": qty}],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# H-1: surface contracts
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_version_header_is_required(client):
    # Plain client without X-Client-Version: rejected before any view runs.
    response = client.get(reverse("mobile_api:product-list"))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "missing_client_version"


@pytest.mark.django_db
def test_protected_endpoints_reject_anonymous(api):
    response = api.get(reverse("mobile_api:order-list"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.django_db
@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
def test_auth_endpoints_throttle_with_429(api):
    url = reverse("mobile_api:login")
    last = None
    # auth-burst is 10/min; the 11th attempt in the window must throttle.
    for _ in range(11):
        last = api.post(
            url,
            {"email": "nobody@example.com", "password": "wrong"},
            content_type="application/json",
        )
    assert last.status_code == 429
    assert last.json()["error"]["code"] == "throttled"


# ---------------------------------------------------------------------------
# H-3: auth lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_register_login_refresh_logout_cycle(api):
    register = api.post(
        reverse("mobile_api:register"),
        {"email": "new@example.com", "password": "s3cretpass!A9", "name": "New"},
        content_type="application/json",
    )
    assert register.status_code == 201
    tokens = register.json()
    assert tokens["customer"]["email"] == "new@example.com"

    refreshed = api.post(
        reverse("mobile_api:refresh"),
        {"refresh": tokens["refresh"]},
        content_type="application/json",
    )
    assert refreshed.status_code == 200
    rotated = refreshed.json()

    logout = api.post(
        reverse("mobile_api:logout"),
        {"refresh": rotated["refresh"]},
        content_type="application/json",
        headers={**VERSION_HEADERS, "authorization": f"Bearer {rotated['access']}"},
    )
    assert logout.status_code == 205

    # The blacklisted refresh token is dead.
    reuse = api.post(
        reverse("mobile_api:refresh"),
        {"refresh": rotated["refresh"]},
        content_type="application/json",
    )
    assert reuse.status_code == 401


@pytest.mark.django_db
def test_registration_claims_matching_guest_orders(api, customer_factory=None):
    variant = _make_variant()
    zone = _make_zone()
    with override_settings(PAYMENT_PROVIDER="simulated"):
        api.post(
            reverse("mobile_api:checkout"),
            json.dumps(_checkout_payload(variant, zone, email="claim@example.com")),
            content_type="application/json",
        )
    register = api.post(
        reverse("mobile_api:register"),
        {"email": "claim@example.com", "password": "s3cretpass!A9", "name": "Claimer"},
        content_type="application/json",
    )
    assert register.status_code == 201
    order = Order.objects.get()
    assert order.customer.email == "claim@example.com"


@pytest.mark.django_db
def test_password_reset_flow(api, customer):
    request = api.post(
        reverse("mobile_api:password-reset"),
        {"email": customer.email},
        content_type="application/json",
    )
    assert request.status_code == 202
    assert len(mail.outbox) == 1
    body = mail.outbox[0].body
    # Deep link carries uid + token back into the app (FR-22).
    uid = body.split("uid=")[1].split("&")[0]
    token = body.split("token=")[1].split()[0]

    confirm = api.post(
        reverse("mobile_api:password-reset-confirm"),
        {"uid": uid, "token": token, "new_password": "n3w-s3cret!B7"},
        content_type="application/json",
    )
    assert confirm.status_code == 200
    customer.refresh_from_db()
    assert customer.check_password("n3w-s3cret!B7")


# ---------------------------------------------------------------------------
# H-2: catalog
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_catalog_list_is_paginated_at_twenty(api):
    category, _ = Category.objects.get_or_create(name="Bulk", slug="bulk")
    for index in range(25):
        Product.objects.create(
            name=f"Bulk {index}", slug=f"bulk-{index}", category=category, base_price=100_00
        )
    response = api.get(reverse("mobile_api:product-list"))
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 20  # NFR-18 hard cap
    assert data["next"] is not None


@pytest.mark.django_db
def test_product_detail_includes_variants_availability_and_reviews(api):
    variant = _make_variant(price_override=120_00)
    response = api.get(reverse("mobile_api:product-detail", args=[variant.product.slug]))
    assert response.status_code == 200
    data = response.json()
    line = data["variants"][0]
    assert line["available"] == 10
    assert line["price"] == 120_00
    assert line["price_display"].startswith("₱")
    assert data["reviews"] == []


# ---------------------------------------------------------------------------
# H-4: cart + checkout (server-authoritative)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cart_validate_uses_server_prices(api):
    variant = _make_variant(base_price=100_00, price_override=150_00)
    response = api.post(
        reverse("mobile_api:cart-validate"),
        # Client-supplied price must be ignored (D-13).
        json.dumps({"items": [{"variant_id": variant.pk, "qty": 2, "price": 1}]}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["lines"][0]["unit_price"] == 150_00
    assert data["subtotal"] == 300_00


@pytest.mark.django_db
@override_settings(PAYMENT_PROVIDER="simulated")
def test_checkout_ignores_client_prices_and_links_holds(api):
    variant = _make_variant(base_price=100_00, price_override=120_00)
    zone = _make_zone()
    payload = _checkout_payload(variant, zone, qty=2)
    # A tampered client claims everything costs one centavo.
    payload["items"][0]["price"] = 1
    payload["total"] = 1

    response = api.post(
        reverse("mobile_api:checkout"), json.dumps(payload), content_type="application/json"
    )

    assert response.status_code == 201, response.content
    data = response.json()
    order = Order.objects.get(order_no=data["order_no"])
    assert order.total == 2 * 120_00 + zone.fee  # server-computed, tamper ignored
    assert data["total"] == order.total
    hold = order.stock_holds.get()
    reservation = Reservation.objects.get(checkout_id=hold.checkout_id)
    assert reservation.status == ReservationStatus.ACTIVE
    assert Payment.objects.get(order=order).status == PaymentStatus.PENDING
    assert data["checkout_url"].startswith("metrodrip://")
    assert "token=" in data["checkout_url"]


@pytest.mark.django_db
@override_settings(PAYMENT_PROVIDER="simulated")
def test_checkout_insufficient_stock_is_conflict_with_rollback(api):
    variant = _make_variant(on_hand=1)
    zone = _make_zone()
    response = api.post(
        reverse("mobile_api:checkout"),
        json.dumps(_checkout_payload(variant, zone, qty=5)),
        content_type="application/json",
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_stock"
    assert Order.objects.count() == 0
    assert StockRecord.objects.get(variant=variant).qty_reserved == 0


# transaction=True so transaction.on_commit fires and the FR-27 notification
# row is actually written (wrapped-test transactions never commit).
@pytest.mark.django_db(transaction=True)
@override_settings(PAYMENT_PROVIDER="simulated")
def test_simulated_confirmation_is_gated_and_idempotent(api, customer):
    variant = _make_variant()
    zone = _make_zone()
    tokens = _login(api, customer)
    checkout = api.post(
        reverse("mobile_api:checkout"),
        json.dumps(_checkout_payload(variant, zone, qty=2)),
        content_type="application/json",
        headers={**VERSION_HEADERS, **_bearer(tokens)},
    ).json()

    confirm_url = reverse("mobile_api:checkout-confirm-simulated")
    first = api.post(
        confirm_url,
        {"status_token": checkout["status_token"]},
        content_type="application/json",
    )
    second = api.post(
        confirm_url,
        {"status_token": checkout["status_token"]},
        content_type="application/json",
    )

    assert first.status_code == 200 and first.json()["status"] == "paid"
    assert second.status_code == 200  # replay: no double effects
    stock = StockRecord.objects.get(variant=variant)
    assert (stock.qty_on_hand, stock.qty_reserved) == (8, 0)
    # FR-27: the Paid transition stored a notification-centre row.
    assert Notification.objects.filter(customer=customer, category="order").count() == 1


@pytest.mark.django_db
def test_simulated_confirmation_404s_under_real_provider(api):
    with override_settings(PAYMENT_PROVIDER="paymongo"):
        response = api.post(
            reverse("mobile_api:checkout-confirm-simulated"),
            {"status_token": "anything"},
            content_type="application/json",
        )
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
@override_settings(PAYMENT_PROVIDER="simulated")
def test_m7_gate_twenty_parallel_api_buyers_for_ten_units(api):
    """M7 QA gate: the M2 no-oversell contract holds when driven via the API."""
    variant = _make_variant(on_hand=10)
    zone = _make_zone()

    start_together = Barrier(20)
    outcomes = Queue()

    def buyer(number):
        from django.db import connections

        connections.close_all()
        buyer_client = Client(headers=VERSION_HEADERS)
        try:
            start_together.wait(timeout=15)
            response = buyer_client.post(
                reverse("mobile_api:checkout"),
                json.dumps(_checkout_payload(variant, zone, qty=1, email=f"b{number}@example.com")),
                content_type="application/json",
            )
            outcomes.put(response.status_code)
        except BaseException as error:  # noqa: BLE001
            outcomes.put(error)
        finally:
            connections.close_all()

    threads = [Thread(target=buyer, args=(n,)) for n in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert all(not thread.is_alive() for thread in threads)

    results = [outcomes.get_nowait() for _ in threads]
    errors = [r for r in results if not isinstance(r, int)]
    assert errors == []
    assert results.count(201) == 10
    assert results.count(409) == 10
    stock = StockRecord.objects.get(variant=variant)
    assert (stock.qty_on_hand, stock.qty_reserved) == (10, 10)
    assert Order.objects.count() == 10


# ---------------------------------------------------------------------------
# H-5/H-6: orders, wishlist, reviews, profile
# ---------------------------------------------------------------------------


def _paid_order_for(api, customer, variant, zone):
    tokens = _login(api, customer)
    with override_settings(PAYMENT_PROVIDER="simulated"):
        checkout = api.post(
            reverse("mobile_api:checkout"),
            json.dumps(_checkout_payload(variant, zone)),
            content_type="application/json",
            headers={**VERSION_HEADERS, **_bearer(tokens)},
        ).json()
        api.post(
            reverse("mobile_api:checkout-confirm-simulated"),
            {"status_token": checkout["status_token"]},
            content_type="application/json",
        )
    return Order.objects.get(order_no=checkout["order_no"]), tokens


@pytest.mark.django_db
def test_order_history_detail_and_guest_tracking(api, customer):
    variant = _make_variant()
    order, tokens = _paid_order_for(api, customer, variant, _make_zone())

    history = api.get(
        reverse("mobile_api:order-list"), headers={**VERSION_HEADERS, **_bearer(tokens)}
    )
    assert history.status_code == 200
    summary = history.json()["results"][0]
    assert summary["order_no"] == order.order_no
    assert summary["status"] == OrderStatus.PAID

    detail = api.get(
        reverse("mobile_api:order-detail", args=[order.order_no]),
        headers={**VERSION_HEADERS, **_bearer(tokens)},
    )
    assert detail.status_code == 200
    payload = detail.json()
    # FR-26: the timeline mirrors the state machine — paid is current.
    states = {step["key"]: step["state"] for step in payload["timeline"]}
    assert states["pending"] == "done" and states["paid"] == "current"

    track = api.get(reverse("mobile_api:order-track", args=[payload["status_token"]]))
    assert track.status_code == 200
    assert track.json()["order_no"] == order.order_no

    # Sequential order numbers are not access credentials (ADR-D-004).
    other = Customer.objects.create_user(email="x@x.test", password="s3cretpass!A9", name="X")
    other_tokens = _login(api, other)
    stranger = api.get(
        reverse("mobile_api:order-detail", args=[order.order_no]),
        headers={**VERSION_HEADERS, **_bearer(other_tokens)},
    )
    assert stranger.status_code == 404


@pytest.mark.django_db
def test_wishlist_toggle_and_listing(api, customer):
    variant = _make_variant()
    tokens = _login(api, customer)
    auth = {**VERSION_HEADERS, **_bearer(tokens)}
    url = reverse("mobile_api:wishlist")

    add = api.post(
        url, {"product_id": variant.product.pk}, content_type="application/json", headers=auth
    )
    assert add.json()["added"] is True
    listing = api.get(url, headers=auth)
    assert listing.json()["results"][0]["in_stock"] is True
    remove = api.post(
        url, {"product_id": variant.product.pk}, content_type="application/json", headers=auth
    )
    assert remove.json()["added"] is False


@pytest.mark.django_db
def test_review_requires_delivered_owned_order(api, customer):
    variant = _make_variant()
    order, tokens = _paid_order_for(api, customer, variant, _make_zone())
    auth = {**VERSION_HEADERS, **_bearer(tokens)}
    payload = {
        "order_no": order.order_no,
        "product_id": variant.product.pk,
        "rating": 5,
        "body": "Solid drip.",
    }
    url = reverse("mobile_api:review-create")

    early = api.post(url, payload, content_type="application/json", headers=auth)
    assert early.status_code == 400  # paid, not yet delivered

    order.transition_to(OrderStatus.PACKED)
    order.transition_to(OrderStatus.SHIPPED)
    order.transition_to(OrderStatus.DELIVERED)

    accepted = api.post(url, payload, content_type="application/json", headers=auth)
    assert accepted.status_code == 201
    assert accepted.json()["status"] == "pending_moderation"


@pytest.mark.django_db
def test_profile_get_and_patch(api, customer):
    tokens = _login(api, customer)
    auth = {**VERSION_HEADERS, **_bearer(tokens)}
    url = reverse("mobile_api:profile")

    assert api.get(url, headers=auth).json()["email"] == customer.email
    patched = api.patch(
        url,
        json.dumps({"name": "Renamed", "phone": "0999"}),
        content_type="application/json",
        headers=auth,
    )
    assert patched.status_code == 200
    customer.refresh_from_db()
    assert customer.name == "Renamed"


# ---------------------------------------------------------------------------
# H-10: devices + notification centre
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_device_registration_and_notification_centre(api, customer):
    tokens = _login(api, customer)
    auth = {**VERSION_HEADERS, **_bearer(tokens)}

    device = api.post(
        reverse("mobile_api:device-register"),
        {"token": "ExponentPushToken[abc123]", "platform": "android"},
        content_type="application/json",
        headers=auth,
    )
    assert device.status_code == 201
    assert DeviceToken.objects.get().customer == customer

    Notification.objects.create(customer=customer, title="Order confirmed", body="x")
    Notification.objects.create(customer=customer, title="On the way", body="y")

    listing = api.get(reverse("mobile_api:notification-list"), headers=auth)
    assert listing.status_code == 200
    data = listing.json()
    assert data["unread_count"] == 2

    first_id = data["results"][0]["id"]
    api.post(reverse("mobile_api:notification-read", args=[first_id]), headers=auth)
    assert Notification.objects.get(pk=first_id).is_read is True

    api.post(reverse("mobile_api:notification-read-all"), headers=auth)
    assert Notification.objects.filter(customer=customer, is_read=False).count() == 0
