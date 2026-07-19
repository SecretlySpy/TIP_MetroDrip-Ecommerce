"""PayMongo adapter and payment-confirmation service (D-2/D-3).

Hard Invariant 3: an order flips Pending → Paid ONLY through
confirm_order_paid(), whose callers are the signature-verified webhook and —
exclusively in development — the MOCK_PAYMENTS sandbox path. Client redirects
never confirm anything.
"""

import base64
import logging

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.inventory.services import (
    InsufficientStock,
    InvalidReservationState,
    commit_reservation,
    reserve_stock,
)
from apps.orders.models import OrderStatus

from .models import Payment, PaymentMethod, PaymentStatus

logger = logging.getLogger(__name__)

PAYMONGO_API_URL = "https://api.paymongo.com/v1"


class PayMongoError(Exception):
    """The provider rejected or failed a checkout-session request."""


def _auth_headers():
    # PayMongo uses HTTP Basic with the secret key as username, empty password.
    b64_auth = base64.b64encode(f"{settings.PAYMONGO_SECRET_KEY}:".encode()).decode()
    return {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def create_checkout_session(order, success_url, cancel_url):
    """Create a hosted checkout session for the order; returns (url, session_id).

    In MOCK_PAYMENTS mode (development without sandbox keys) no network call is
    made: a pending Payment is recorded and the shopper is sent straight to the
    success URL, where the mock confirmation path completes the flow.
    """
    if settings.MOCK_PAYMENTS:
        Payment.objects.create(
            order=order,
            provider_ref=f"mock_session_{order.order_no}",
            method=PaymentMethod.CARD,
            status=PaymentStatus.PENDING,
            amount=order.total,
        )
        separator = "&" if "?" in success_url else "?"
        return f"{success_url}{separator}mock=1", f"mock_session_{order.order_no}"

    line_items = [
        {
            "name": f"{item.variant.product.name} ({item.variant.sku})",
            "quantity": item.qty,
            # Snapshot price, not live catalog price: the shopper pays what
            # checkout displayed even if the catalog changed since.
            "amount": item.unit_price_snapshot,
            "currency": "PHP",
        }
        for item in order.items.select_related("variant__product")
    ]
    if order.shipping_fee > 0:
        line_items.append(
            {"name": "Shipping Fee", "quantity": 1, "amount": order.shipping_fee, "currency": "PHP"}
        )

    payload = {
        "data": {
            "attributes": {
                "billing": {
                    "name": order.shipping_address.get("name"),
                    "email": order.shipping_address.get("email"),
                    "phone": order.shipping_address.get("phone"),
                },
                "send_email_receipt": False,
                "show_description": True,
                "show_line_items": True,
                "line_items": line_items,
                # FR-4: cards, GCash, Maya (PayMongo's identifier is "paymaya").
                "payment_method_types": ["card", "gcash", "paymaya"],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "reference_number": order.order_no,
                "description": f"MetroDrip Order {order.order_no}",
            }
        }
    }

    response = requests.post(
        f"{PAYMONGO_API_URL}/checkout_sessions",
        json=payload,
        headers=_auth_headers(),
        timeout=10,
    )
    if response.status_code != 200:
        # Never bubble raw provider text to shoppers; the caller logs and maps
        # this to a friendly retryable error.
        raise PayMongoError(f"PayMongo checkout session failed with HTTP {response.status_code}")

    data = response.json().get("data", {})
    session_id = data.get("id")
    checkout_url = data.get("attributes", {}).get("checkout_url")
    if not session_id or not checkout_url:
        raise PayMongoError("PayMongo response missing session id or checkout URL")

    Payment.objects.create(
        order=order,
        provider_ref=session_id,
        method=PaymentMethod.CARD,  # placeholder until the webhook reports the real method
        status=PaymentStatus.PENDING,
        amount=order.total,
    )
    return checkout_url, session_id


def confirm_order_paid(*, order, method=None):
    """Idempotently flip an order to Paid and consume its stock holds (D-3).

    Returns True on first confirmation, False when the payment was already
    processed (webhook replays are a supported, expected case).

    Stock semantics: commits the reservations linked to the order at checkout.
    If a hold expired before the webhook arrived, the shopper still paid — try
    a fresh reserve+commit; if stock is truly gone, log CRITICAL for a manual
    E-4 refund instead of overselling.
    """
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(order=order)
        if payment.status == PaymentStatus.PAID:
            return False

        payment.status = PaymentStatus.PAID
        payment.paid_at = timezone.now()
        update_fields = ["status", "paid_at"]
        if method in PaymentMethod.values:
            payment.method = method
            update_fields.append("method")
        payment.save(update_fields=update_fields)

        # Consume this order's own holds — never another shopper's.
        committed_by_variant = {}
        for reservation in order.reservations.filter(status="active"):
            try:
                commit_reservation(reservation_id=reservation.pk, order=order)
                committed_by_variant[reservation.variant_id] = (
                    committed_by_variant.get(reservation.variant_id, 0) + reservation.qty
                )
            except InvalidReservationState:
                # Lost a race with the TTL sweep; the per-item fallback below
                # re-reserves whatever this hold should have covered.
                logger.warning(
                    "Order %s: reservation %s not committable", order.order_no, reservation.pk
                )

        for item in order.items.all():
            shortfall = item.qty - committed_by_variant.get(item.variant_id, 0)
            if shortfall <= 0:
                continue
            try:
                replacement = reserve_stock(variant_id=item.variant_id, qty=shortfall, order=order)
                commit_reservation(reservation_id=replacement.pk, order=order)
            except InsufficientStock:
                # Paid but unfillable: never oversell (Invariant 1); surface for
                # the manual cancel/refund flow instead.
                logger.critical(
                    "Order %s PAID but variant %s short by %d units — manual refund needed",
                    order.order_no,
                    item.variant_id,
                    shortfall,
                )

        order.transition_to(OrderStatus.PAID)
    return True
