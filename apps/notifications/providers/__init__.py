"""Notification provider interface and registry."""

import abc

from django.conf import settings


class NotificationProvider(abc.ABC):
    """Contract every notification adapter must satisfy."""

    @abc.abstractmethod
    def send_order_confirmation(self, order, status_url):
        """Send order confirmation to shopper."""

    @abc.abstractmethod
    def send_contact_alert(self, contact_message):
        """Send contact form alert to staff."""

    @abc.abstractmethod
    def send_low_stock_alert(self, records):
        """Send low stock alert to staff."""

    @abc.abstractmethod
    def send_sms(self, phone_number, message):
        """Send SMS message."""


_registry = {}


def register_provider(name):
    """Class decorator: register a NotificationProvider under *name*."""

    def decorator(cls):
        _registry[name] = cls
        return cls

    return decorator


def get_notification_provider() -> NotificationProvider:
    """Return the singleton provider selected by settings."""
    name = getattr(settings, "NOTIFICATION_PROVIDER", "console")
    cls = _registry.get(name)
    if cls is None:
        raise ValueError(f"Unknown notification provider: {name!r}")
    return cls()
