"""Integer-centavo validation, arithmetic, and Philippine-peso formatting."""

from collections.abc import Iterable

from django.conf import settings

# Django's PositiveIntegerField maps to MySQL INT UNSIGNED. Checking the same
# ceiling before arithmetic produces a domain error instead of a late DB failure.
MAX_CENTAVOS = 4_294_967_295


class MoneyValueError(ValueError):
    """Raised when a value violates MetroDrip's integer-centavo contract."""


def require_centavos(value, field_name="amount", *, allow_negative=False):
    """Return a valid centavo integer or raise a field-specific domain error."""
    # bool subclasses int in Python, but accepting True as one centavo would hide
    # form/API bugs. Every accepted monetary value must be an actual integer.
    if isinstance(value, bool) or not isinstance(value, int):
        raise MoneyValueError(f"{field_name} must be an integer number of centavos.")

    if not allow_negative and value < 0:
        raise MoneyValueError(f"{field_name} cannot be negative.")

    # Negative values are useful for report display, but their absolute value
    # still shares the persisted unsigned-INT magnitude ceiling.
    if abs(value) > MAX_CENTAVOS:
        raise MoneyValueError(f"{field_name} exceeds the MySQL INT centavo limit.")

    return value


def format_centavos(value, symbol=None):
    """Format an integer centavo value as a grouped peso amount."""
    amount = require_centavos(value, allow_negative=True)
    selected_symbol = settings.CURRENCY_SYMBOL if symbol is None else symbol
    if not isinstance(selected_symbol, str):
        raise MoneyValueError("currency symbol must be a string.")

    # Work with the absolute magnitude so negative output consistently places
    # the sign before the currency symbol: -₱1.23.
    pesos, centavos = divmod(abs(amount), 100)
    sign = "-" if amount < 0 else ""
    return f"{sign}{selected_symbol}{pesos:,}.{centavos:02d}"


def multiply_centavos(unit_price, quantity):
    """Calculate one order-line total without floating-point arithmetic."""
    price = require_centavos(unit_price, "unit_price")
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise MoneyValueError("quantity must be an integer.")
    if quantity < 1:
        raise MoneyValueError("quantity must be at least 1.")

    line_total = price * quantity
    return require_centavos(line_total, "line_total")


def sum_centavos(amounts: Iterable[int]):
    """Sum nonnegative centavo values and fail immediately on overflow."""
    total = 0
    for index, amount in enumerate(amounts):
        # Including the index turns a malformed cart/report input into an
        # actionable error without accepting strings, decimals, or floats.
        total += require_centavos(amount, f"amounts[{index}]")
        require_centavos(total, "total")
    return total
