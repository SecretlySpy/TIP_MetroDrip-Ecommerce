"""Shipping provider interface and registry.

Domain code calls `get_shipping_provider()` to obtain the active implementation.
"""

import abc

from django.conf import settings


class ShippingProvider(abc.ABC):
    """Contract every shipping adapter must satisfy."""

    @abc.abstractmethod
    def book_shipment(self, shipment):
        """Simulate or actual booking of a shipment.

        Returns True if successfully booked, False otherwise (e.g. invalid state).
        Updates shipment.waybill_no, tracking_url, status, and booked_at.
        """


_registry = {}


def register_provider(name):
    """Class decorator: register a ShippingProvider under *name*."""

    def decorator(cls):
        _registry[name] = cls
        return cls

    return decorator


def get_shipping_provider() -> ShippingProvider:
    """Return the singleton provider selected by settings."""
    name = getattr(settings, "SHIPPING_PROVIDER", "simulated")
    cls = _registry.get(name)
    if cls is None:
        raise ValueError(f"Unknown shipping provider: {name!r}")
    return cls()
