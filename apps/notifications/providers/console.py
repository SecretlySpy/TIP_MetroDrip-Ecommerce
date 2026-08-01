"""Console notification provider for simulated/dev mode."""

import logging

from . import NotificationProvider, register_provider
from apps.orders.money import format_centavos

logger = logging.getLogger(__name__)


@register_provider("console")
class ConsoleNotificationProvider(NotificationProvider):
    """Outputs notifications to the console via logger.info."""

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
        logger.info(f"CONSOLE EMAIL to {email}:\nSubject: MetroDrip order {order.order_no} confirmed\n\n{body}")
        return True

    def send_contact_alert(self, contact_message):
        logger.info(
            f"CONSOLE EMAIL (Contact Alert):\nFrom: {contact_message.name} <{contact_message.email}>\n\n{contact_message.message}"
        )
        return True

    def send_low_stock_alert(self, records):
        records = list(records)
        if not records:
            return 0

        lines = [
            f"{record.variant.sku}: available {record.available} "
            f"(on hand {record.qty_on_hand}, reserved {record.qty_reserved}, "
            f"threshold {record.low_stock_threshold})"
            for record in records
        ]
        logger.info(f"CONSOLE EMAIL (Low Stock Alert):\n" + "\n".join(lines))
        return len(records)

    def send_sms(self, phone_number, message):
        logger.info(f"CONSOLE SMS to {phone_number}: {message}")
        return True
