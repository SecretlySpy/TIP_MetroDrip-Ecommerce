"""Payment provider interface and registry.

Domain code calls `get_payment_provider()` to obtain the active implementation.
The concrete class is selected by `settings.PAYMENT_PROVIDER`:

    "simulated"  — SimulatedPaymentProvider  (dev/free-tier hosting)
    "paymongo"   — PayMongoPaymentProvider   (production)
"""

import abc

from django.conf import settings


class PaymentProvider(abc.ABC):
    """Contract every payment adapter must satisfy."""

    @abc.abstractmethod
    def create_checkout_session(self, order, success_url, cancel_url):
        """Return (checkout_url, provider_ref) for the order."""

    @abc.abstractmethod
    def confirm_order_paid(self, *, order, method=None):
        """Idempotently flip order to Paid and consume stock holds.

        Returns True on first confirmation, False on replay.
        """


_registry = {}


def register_provider(name):
    """Class decorator: register a PaymentProvider under *name*."""

    def decorator(cls):
        _registry[name] = cls
        return cls

    return decorator


def get_payment_provider() -> PaymentProvider:
    """Return the singleton provider selected by settings."""
    name = getattr(settings, "PAYMENT_PROVIDER", "simulated")
    cls = _registry.get(name)
    if cls is None:
        raise ValueError(f"Unknown payment provider: {name!r}")
    return cls()
