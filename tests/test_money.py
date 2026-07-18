"""Executable contracts for integer-centavo arithmetic and peso presentation.

These tests intentionally keep storage concerns separate from presentation:
domain helpers fail loudly when money is malformed, while the storefront filter
fails closed so an unexpected template value cannot turn into a page-level 500.
"""

from decimal import Decimal

import pytest
from django.conf import settings
from django.template import Context, Template
from django.test import override_settings

from apps.orders.money import (
    MAX_CENTAVOS,
    MoneyValueError,
    format_centavos,
    multiply_centavos,
    require_centavos,
    sum_centavos,
)
from apps.storefront.templatetags import money as money_tags


def test_money_configuration_uses_the_locked_php_defaults():
    """A single currency contract prevents storage and display from drifting apart."""
    assert settings.CURRENCY_CODE == "PHP"
    assert settings.CURRENCY_SYMBOL == "₱"
    assert settings.CURRENCY_MINOR_UNITS == 2


def test_max_centavos_matches_the_unsigned_mysql_int_boundary():
    """Money validation must match the schema instead of accepting unpersistable values."""
    assert MAX_CENTAVOS == 4_294_967_295


def test_money_value_error_is_a_value_error():
    """Callers should be able to catch either the focused error or normal value errors."""
    assert issubclass(MoneyValueError, ValueError)


@pytest.mark.parametrize("value", [0, 1, 123_456, MAX_CENTAVOS])
def test_require_centavos_returns_valid_nonnegative_integers_unchanged(value):
    """Validated centavos remain integers so no precision-changing conversion occurs."""
    assert require_centavos(value) == value


@pytest.mark.parametrize(
    "invalid_value",
    [True, False, 1.0, Decimal("1"), "100", "", None],
)
def test_require_centavos_rejects_non_integer_values(invalid_value):
    """Python's bool-is-an-int quirk and coercible inputs must not weaken money typing."""
    with pytest.raises(MoneyValueError):
        require_centavos(invalid_value)


def test_require_centavos_uses_the_field_name_in_validation_errors():
    """A caller-supplied field name makes failures actionable at service boundaries."""
    with pytest.raises(MoneyValueError, match="subtotal"):
        require_centavos("100", field_name="subtotal")


def test_require_centavos_rejects_negative_values_by_default():
    """Ordinary prices and totals cannot silently become refunds or credits."""
    with pytest.raises(MoneyValueError):
        require_centavos(-1)


@pytest.mark.parametrize("value", [-1, -12_345, -MAX_CENTAVOS])
def test_require_centavos_allows_bounded_negatives_only_when_explicit(value):
    """Signed adjustments require an explicit opt-in at the exact call site."""
    assert require_centavos(value, allow_negative=True) == value


@pytest.mark.parametrize(
    ("value", "allow_negative"),
    [
        (MAX_CENTAVOS + 1, False),
        (MAX_CENTAVOS + 1, True),
        (-(MAX_CENTAVOS + 1), True),
    ],
)
def test_require_centavos_rejects_values_outside_the_storage_boundary(
    value,
    allow_negative,
):
    """Even explicitly signed values must remain inside the documented magnitude bound."""
    with pytest.raises(MoneyValueError):
        require_centavos(value, allow_negative=allow_negative)


@pytest.mark.parametrize(
    ("centavos", "expected"),
    [
        (0, "₱0.00"),
        (1, "₱0.01"),
        (99, "₱0.99"),
        (100, "₱1.00"),
        (123_456, "₱1,234.56"),
        (MAX_CENTAVOS, "₱42,949,672.95"),
    ],
)
def test_format_centavos_renders_exact_peso_amounts(centavos, expected):
    """Formatting happens without floats and always shows both PHP minor-unit digits."""
    assert format_centavos(centavos) == expected


@pytest.mark.parametrize(
    "invalid_value",
    [-1, True, 1.5, Decimal("1.00"), "100", None],
)
def test_format_centavos_rejects_invalid_or_implicitly_negative_values(invalid_value):
    """Display formatting must not become an accidental coercion or signed-money API."""
    with pytest.raises(MoneyValueError):
        format_centavos(invalid_value)


def test_format_centavos_accepts_an_explicit_symbol_override():
    """Exports can replace or omit the glyph without changing the stored amount."""
    assert format_centavos(12_345, symbol="PHP ") == "PHP 123.45"
    assert format_centavos(12_345, symbol="") == "123.45"


@override_settings(CURRENCY_SYMBOL="P", CURRENCY_MINOR_UNITS=3)
def test_format_centavos_reads_runtime_currency_settings():
    """The formatter must honor deployment settings rather than copy PHP literals."""
    assert format_centavos(123_456) == "P123.456"


@pytest.mark.parametrize(
    ("unit_price", "quantity", "expected"),
    [
        (0, 1, 0),
        (125, 3, 375),
        (1_234_567, 25, 30_864_175),
        (MAX_CENTAVOS, 1, MAX_CENTAVOS),
    ],
)
def test_multiply_centavos_returns_exact_integer_line_totals(
    unit_price,
    quantity,
    expected,
):
    """Order-line multiplication stays exact and validates its persisted result."""
    assert multiply_centavos(unit_price, quantity) == expected


@pytest.mark.parametrize("invalid_quantity", [0, -1, True, 1.0, "2", None])
def test_multiply_centavos_rejects_invalid_quantities(invalid_quantity):
    """A line item must contain a positive, non-boolean integer quantity."""
    with pytest.raises(MoneyValueError):
        multiply_centavos(100, invalid_quantity)


@pytest.mark.parametrize("invalid_price", [-1, True, 1.0, Decimal("1"), "100", None])
def test_multiply_centavos_rejects_invalid_unit_prices(invalid_price):
    """Multiplication must validate its operands before Python can coerce their types."""
    with pytest.raises(MoneyValueError):
        multiply_centavos(invalid_price, 2)


def test_multiply_centavos_rejects_an_overflowed_line_total():
    """A valid unit price can still produce a result too large for the database column."""
    with pytest.raises(MoneyValueError):
        multiply_centavos(MAX_CENTAVOS, 2)


def test_sum_centavos_supports_empty_and_materialized_iterables():
    """An empty cart has a zero subtotal and ordinary collections sum exactly."""
    assert sum_centavos([]) == 0
    assert sum_centavos([100, 250, 650]) == 1_000
    assert sum_centavos((1, 2, 3)) == 6


def test_sum_centavos_consumes_a_generator_once():
    """Services may stream line totals without materializing a second collection."""
    amounts = (amount for amount in [100, 200, 300])

    assert sum_centavos(amounts) == 600
    assert list(amounts) == []


@pytest.mark.parametrize("invalid_amount", [-1, True, 1.0, Decimal("1"), "100", None])
def test_sum_centavos_rejects_invalid_iterable_members(invalid_amount):
    """One malformed line must invalidate the subtotal instead of being coerced."""
    with pytest.raises(MoneyValueError):
        sum_centavos([100, invalid_amount])


def test_sum_centavos_rejects_an_overflowed_aggregate():
    """Individually valid amounts may not produce an unpersistable aggregate total."""
    with pytest.raises(MoneyValueError):
        sum_centavos([MAX_CENTAVOS, 1])


def test_peso_filter_delegates_valid_integers_to_the_domain_formatter(monkeypatch):
    """The template layer should have one formatting source of truth, not duplicate math."""
    received_values = []

    def fake_format_centavos(value):
        # Recording the value proves the filter passes it through without conversion.
        received_values.append(value)
        return "formatted-by-domain-helper"

    monkeypatch.setattr(money_tags, "format_centavos", fake_format_centavos)

    assert money_tags.peso(12_345) == "formatted-by-domain-helper"
    assert received_values == [12_345]


def test_peso_filter_is_registered_and_formats_template_values():
    """Loading the tag library verifies Django can discover the public ``peso`` filter."""
    rendered = Template("{% load money %}{{ amount|peso }}").render(Context({"amount": 123_456}))

    assert rendered == "₱1,234.56"


@pytest.mark.parametrize("invalid_value", [-1, True, 1.5, Decimal("1"), "100", None])
def test_peso_filter_fails_closed_for_invalid_template_context(invalid_value):
    """Malformed presentation data must render blank instead of crashing the storefront."""
    assert money_tags.peso(invalid_value) == ""
