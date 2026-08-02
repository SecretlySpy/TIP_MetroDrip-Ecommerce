"""Push delivery + order-event fan-out (FR-27).

Provider-selected like payments/shipping: `PUSH_PROVIDER = "simulated" | "expo"`.
Simulated logs instead of sending, per D-08 — enhancement-tier delivery that
must never block or break a business transition.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# Order statuses that notify the shopper, with customer-facing copy (FR-27).
ORDER_EVENT_COPY = {
    "paid": ("Order confirmed", "Payment received for {order_no}. We're getting it ready."),
    "packed": ("Packed and ready", "{order_no} is packed and awaiting courier pickup."),
    "shipped": ("On the way", "{order_no} has shipped. Track it live in the app."),
    "delivered": ("Delivered", "{order_no} was delivered. Enjoy the drip!"),
    "cancelled": ("Order cancelled", "{order_no} was cancelled. Holds have been released."),
    "refunded": ("Refund issued", "Your refund for {order_no} is on its way."),
}

# Shipment-level event that has no order-status counterpart (FR-12/FR-27).
OUT_FOR_DELIVERY_COPY = ("Out for delivery", "{order_no} is out for delivery today.")


def send_push(device_tokens, title, body, data=None):
    """Deliver one push message to a list of Expo tokens; returns sent count.

    Failures are logged, never raised — a push outage must not fail an order
    transition or a webhook (§7 enhancement-tier rule).
    """
    tokens = [t for t in device_tokens if t]
    if not tokens:
        return 0

    if getattr(settings, "PUSH_PROVIDER", "simulated") != "expo":
        logger.info("[push simulated] %d device(s): %s — %s", len(tokens), title, body)
        return len(tokens)

    try:
        messages = [
            {"to": token, "title": title, "body": body, "data": data or {}, "sound": "default"}
            for token in tokens
        ]
        response = requests.post(EXPO_PUSH_URL, json=messages, timeout=10)
        response.raise_for_status()
        return len(tokens)
    except Exception:
        logger.exception("Expo push delivery failed (%d device(s))", len(tokens))
        return 0


def notify_customer(customer, *, title, body, category="order", order=None):
    """Store the notification-centre row (FR-28) and push it to all devices."""
    # Local import: this module is imported from models via transaction.on_commit
    # callbacks, so keep import-time dependencies one-directional.
    from .models import Notification

    Notification.objects.create(
        customer=customer, title=title, body=body, category=category, order=order
    )
    send_push(
        customer.device_tokens.values_list("token", flat=True),
        title,
        body,
        data={"category": category, "order_no": order.order_no if order else None},
    )


def notify_order_event(order, status):
    """Fan out one order-lifecycle event; silently skips guests (no account)."""
    copy = ORDER_EVENT_COPY.get(str(status))
    if copy is None or order.customer_id is None:
        return
    title, body_template = copy
    try:
        notify_customer(
            order.customer,
            title=title,
            body=body_template.format(order_no=order.order_no),
            category="order",
            order=order,
        )
    except Exception:
        logger.exception("Order notification failed for %s → %s", order.order_no, status)


def notify_out_for_delivery(shipment):
    """Shipment-level Out-for-Delivery event (FR-27's fourth trigger)."""
    order = shipment.order
    if order.customer_id is None:
        return
    title, body_template = OUT_FOR_DELIVERY_COPY
    try:
        notify_customer(
            order.customer,
            title=title,
            body=body_template.format(order_no=order.order_no),
            category="order",
            order=order,
        )
    except Exception:
        logger.exception("Out-for-delivery notification failed for %s", order.order_no)
