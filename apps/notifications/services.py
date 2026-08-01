"""Notification services facade delegating to the active NotificationProvider."""

import logging

from .providers import get_notification_provider

logger = logging.getLogger(__name__)

# Re-export for compatibility with existing callers
__all__ = ["send_order_confirmation", "send_contact_alert", "send_low_stock_alert"]


def send_order_confirmation(order, status_url):
    return get_notification_provider().send_order_confirmation(order, status_url)


def send_contact_alert(contact_message):
    return get_notification_provider().send_contact_alert(contact_message)


def send_low_stock_alert(records):
    return get_notification_provider().send_low_stock_alert(records)
