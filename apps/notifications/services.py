"""Notification adapters (§8): low-stock alerts (FR-9), order confirmation
email (FR-11), and contact-form staff alerts (FR-18). Semaphore SMS lives in
apps/notifications/sms.py behind the same graceful-degradation rule.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

from apps.orders.money import format_centavos

logger = logging.getLogger(__name__)


def send_order_confirmation(order, status_url):
    """Email the shopper their order summary and tokenized tracking link (FR-11).

    Returns True when a message was sent. Guests are reached through the
    contact email captured in the checkout snapshot.
    """
    email = order.shipping_address.get("email")
    if not email:
        logger.warning("Order %s has no contact email; skipping confirmation.", order.order_no)
        return False

    lines = [
        f"  {item.qty} × {item.variant.product.name} ({item.variant.sku}) — "
        f"{format_centavos(item.unit_price_snapshot * item.qty)}"
        for item in order.items.select_related("variant__product")
    ]
    body = (
        f"Thanks for your order!\n\n"
        f"Order {order.order_no}\n\n"
        + "\n".join(lines)
        + f"\n\n  Subtotal: {format_centavos(order.subtotal)}"
        f"\n  Shipping: {format_centavos(order.shipping_fee)}"
        f"\n  Total:    {format_centavos(order.total)}"
        f"\n\nTrack your order any time:\n{status_url}\n"
    )
    send_mail(
        subject=f"MetroDrip order {order.order_no} confirmed",
        message=body,
        from_email=None,  # DEFAULT_FROM_EMAIL
        recipient_list=[email],
    )
    return True


def send_contact_alert(contact_message):
    """Forward a stored contact-form submission to staff (FR-18); store-only
    when no recipients are configured."""
    recipients = settings.CONTACT_ALERT_RECIPIENTS
    if not recipients:
        logger.info(
            "Contact message %s stored; no alert recipients configured.", contact_message.pk
        )
        return False
    send_mail(
        subject=f"[MetroDrip] Contact form: {contact_message.name}",
        message=(
            f"From: {contact_message.name} <{contact_message.email}>\n\n{contact_message.message}"
        ),
        from_email=None,
        recipient_list=recipients,
    )
    return True


def send_low_stock_alert(records):
    """Email the low-stock SKU list to configured staff (FR-9); returns sent count.

    With no recipients configured the alert degrades to a log line — alerting
    is an enhancement around the scan, never a hard dependency, mirroring the
    handover's graceful-degradation rule for notification channels.
    """
    records = list(records)
    if not records:
        return 0

    recipients = settings.LOW_STOCK_ALERT_RECIPIENTS
    if not recipients:
        logger.info(
            "Low-stock scan flagged %d SKU(s); no alert recipients configured.", len(records)
        )
        return 0

    lines = [
        f"{record.variant.sku}: available {record.available} "
        f"(on hand {record.qty_on_hand}, reserved {record.qty_reserved}, "
        f"threshold {record.low_stock_threshold})"
        for record in records
    ]
    send_mail(
        subject=f"[MetroDrip] Low stock: {len(records)} SKU(s) at or below threshold",
        message="The following SKUs need restocking:\n\n" + "\n".join(lines),
        from_email=None,  # DEFAULT_FROM_EMAIL
        recipient_list=recipients,
    )
    return len(records)
