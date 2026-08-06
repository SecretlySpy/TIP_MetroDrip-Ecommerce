"""Inventory domain exceptions, shared by every provider implementation."""


class InsufficientStock(Exception):
    """Business rejection: the requested units exceed available (= on_hand − reserved)."""


class InvalidReservationState(Exception):
    """The reservation is not in a state that permits the requested action."""


class InvalidStockAdjustment(Exception):
    """The adjustment would corrupt counters or uses a reason reserved for sales."""


class ReservationUnavailable(Exception):
    """The stock ledger could not be reached, or its answer was uncertain.

    Distinct from InsufficientStock, which is a definite "no". This one means
    the caller does not know whether stock was held, so it must compensate by
    releasing its `checkout_id` — a no-op if nothing was ever reserved — rather
    than assuming either outcome.
    """
