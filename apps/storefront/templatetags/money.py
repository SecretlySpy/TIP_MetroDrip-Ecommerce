"""Template-safe presentation filters for integer-centavo values."""

from django import template

from apps.orders.money import MoneyValueError, format_centavos

register = template.Library()


@register.filter(name="peso")
def peso(value):
    """Render valid centavos as pesos and suppress malformed template values."""
    try:
        return format_centavos(value)
    except MoneyValueError:
        # Templates should not turn one missing/invalid display value into a 500
        # response. Domain services remain strict and raise the original error.
        return ""
