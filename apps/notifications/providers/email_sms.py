"""Email and SMS notification provider (real implementations)."""

import logging
import os

import requests
from django.conf import settings
from django.core.mail import send_mail

from apps.orders.money import format_centavos

from . import NotificationProvider, register_provider

logger = logging.getLogger(__name__)

SEMAPHORE_API_KEY = getattr(settings, "SEMAPHORE_API_KEY", os.environ.get("SEMAPHORE_API_KEY", ""))
SEMAPHORE_SENDER_NAME = getattr(
    settings, "SEMAPHORE_SENDER_NAME", os.environ.get("SEMAPHORE_SENDER_NAME", "MetroDrip")
)


@register_provider("email_sms")
class EmailSmsNotificationProvider(NotificationProvider):
    """Real email and Semaphore SMS adapter."""

    def send_order_confirmation(self, order, status_url):
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

    def send_contact_alert(self, contact_message):
        recipients = settings.CONTACT_ALERT_RECIPIENTS
        if not recipients:
            logger.info(
                "Contact message %s stored; no alert recipients configured.", contact_message.pk
            )
            return False
        send_mail(
            subject=f"[MetroDrip] Contact form: {contact_message.name}",
            message=(
                f"From: {contact_message.name} <{contact_message.email}>\n\n"
                f"{contact_message.message}"
            ),
            from_email=None,
            recipient_list=recipients,
        )
        return True

    def send_low_stock_alert(self, records):
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

    def send_sms(self, phone_number, message):
        if not SEMAPHORE_API_KEY:
            logger.info(f"SMS mocked for {phone_number}: {message}")
            return False

        try:
            response = requests.post(
                "https://api.semaphore.co/api/v4/messages",
                data={
                    "apikey": SEMAPHORE_API_KEY,
                    "number": phone_number,
                    "message": message,
                    "sendername": SEMAPHORE_SENDER_NAME,
                },
                timeout=5,
            )
            response.raise_for_status()
            logger.info(f"SMS sent successfully to {phone_number}")
            return True
        except Exception as e:
            logger.warning(f"Failed to send SMS to {phone_number}: {str(e)}")
            return False
