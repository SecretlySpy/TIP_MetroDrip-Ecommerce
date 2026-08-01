"""SMS services facade delegating to the active NotificationProvider."""

import logging

from .providers import get_notification_provider

logger = logging.getLogger(__name__)

# Re-export for compatibility with existing callers
__all__ = ["send_sms"]


def send_sms(phone_number, message):
    return get_notification_provider().send_sms(phone_number, message)
