"""Order business logic. Views stay thin (§8); all order mutations route here."""

from django.db import transaction
from django.utils import timezone

from .models import MAX_ORDER_SEQUENCE, OrderNumberSequence


class InvalidOrderYear(ValueError):
    """Raised when an allocator caller supplies a non-four-digit business year."""


class OrderNumberExhausted(RuntimeError):
    """Raised after all 99,999 order numbers for one year have been allocated."""


def next_order_no(year=None):
    """Allocate the next MD-YYYY-NNNNN order number, race-safely.

    Locks the per-year sequence row so two concurrent checkouts can never mint
    the same number. Must be called inside the checkout's outer transaction —
    transaction.atomic here is a no-op join in that case, a standalone txn otherwise.
    """
    if year is None:
        year = timezone.localdate().year  # Asia/Manila business year, not UTC
    if isinstance(year, bool) or not isinstance(year, int) or not 1000 <= year <= 9999:
        raise InvalidOrderYear("Order year must be a four-digit integer from 1000 to 9999.")

    with transaction.atomic():
        # Django's get_or_create handles the unique-row insertion race; the
        # select_for_update queryset locks either the existing or recovered row.
        seq, _ = OrderNumberSequence.objects.select_for_update().get_or_create(year=year)
        if seq.last_value >= MAX_ORDER_SEQUENCE:
            raise OrderNumberExhausted(f"Order number sequence for {year} is exhausted.")

        seq.last_value += 1
        seq.save(update_fields=["last_value"])
        return f"MD-{year}-{seq.last_value:05d}"
