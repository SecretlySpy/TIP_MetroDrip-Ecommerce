"""Inventory domain exceptions, shared by every provider implementation."""


class InsufficientStock(Exception):
    """Business rejection: the requested units exceed available (= on_hand − reserved)."""


class InvalidReservationState(Exception):
    """The reservation is not in a state that permits the requested action."""


class InvalidStockAdjustment(Exception):
    """The adjustment would corrupt counters or uses a reason reserved for sales."""
