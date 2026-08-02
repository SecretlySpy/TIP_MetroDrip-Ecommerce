"""Inventory service facade (§8): the single import point for stock operations.

Delegates to the provider selected by `INVENTORY_PROVIDER` ("local" by default —
the in-process, row-locked implementation that upholds Hard Invariants 1 & 4;
"service" opts into the experimental D-07 FastAPI client). Domain exceptions
are re-exported here so callers never import provider modules directly.
"""

from .exceptions import (  # noqa: F401 — public API re-exports
    InsufficientStock,
    InvalidReservationState,
    InvalidStockAdjustment,
)


def _provider():
    # Resolved per call so tests and settings overrides always take effect.
    from .providers import get_inventory_provider

    return get_inventory_provider()


def reserve_stock(*, variant_id, qty, session_key="", order=None):
    return _provider().reserve_stock(
        variant_id=variant_id, qty=qty, session_key=session_key, order=order
    )


def release_reservation(reservation_id):
    return _provider().release_reservation(reservation_id)


def commit_reservation(*, reservation_id, order):
    return _provider().commit_reservation(reservation_id=reservation_id, order=order)


def adjust_stock(*, variant_id, delta, reason, ref_order=None):
    return _provider().adjust_stock(
        variant_id=variant_id, delta=delta, reason=reason, ref_order=ref_order
    )


def release_expired_reservations(now=None):
    return _provider().release_expired_reservations(now=now)


def scan_low_stock():
    return _provider().scan_low_stock()


def get_stock_record(variant_id):
    return _provider().get_stock_record(variant_id)
