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
    ReservationUnavailable,
)


def _provider():
    # Resolved per call so tests and settings overrides always take effect.
    from .providers import get_inventory_provider

    return get_inventory_provider()


def reserve_stock(*, variant_id, qty, session_key="", order=None, checkout_id=""):
    return _provider().reserve_stock(
        variant_id=variant_id,
        qty=qty,
        session_key=session_key,
        order=order,
        checkout_id=checkout_id,
    )


def reserve_lines(*, checkout_id, lines, session_key="", ttl_minutes=None):
    """Reserve a whole cart atomically under one `checkout_id`."""
    return _provider().reserve_lines(
        checkout_id=checkout_id, lines=lines, session_key=session_key, ttl_minutes=ttl_minutes
    )


def commit_holds(*, checkout_id, order_no="", order_id=None):
    """Turn a checkout group's holds into sales; safe to replay."""
    return _provider().commit_holds(checkout_id=checkout_id, order_no=order_no, order_id=order_id)


def release_holds(*, checkout_id):
    """Compensation: release a checkout group's holds. Unknown ids are a no-op."""
    return _provider().release_holds(checkout_id=checkout_id)


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


def get_stock_records(variant_ids):
    """Counters for many SKUs as `{variant_id: record}` — one call, not N.

    Prefer this anywhere a page reads stock for a set of variants. Under
    `INVENTORY_PROVIDER=service` the single-record accessor is one HTTP round
    trip each, so a loop over it is a per-request fan-out.
    """
    return _provider().get_stock_records(variant_ids)
