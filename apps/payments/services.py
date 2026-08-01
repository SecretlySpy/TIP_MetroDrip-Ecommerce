"""Payment services facade delegating to the active PaymentProvider."""

import logging

from .providers import get_payment_provider
from .providers.paymongo import PayMongoError

logger = logging.getLogger(__name__)

# Re-export for compatibility with existing callers
__all__ = ["create_checkout_session", "confirm_order_paid", "PayMongoError"]


def create_checkout_session(order, success_url, cancel_url):
    """Create a hosted checkout session for the order; returns (url, session_id)."""
    return get_payment_provider().create_checkout_session(order, success_url, cancel_url)


def confirm_order_paid(*, order, method=None):
    """Idempotently flip an order to Paid and consume its stock holds."""
    return get_payment_provider().confirm_order_paid(order=order, method=method)
