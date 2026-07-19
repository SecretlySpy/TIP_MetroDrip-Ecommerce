"""General storefront template helpers (tokenized links, peso aliases)."""

from django import template
from django.core.signing import Signer

from apps.orders.money import MoneyValueError
from apps.orders.money import format_centavos as _format_centavos

register = template.Library()


@register.filter(name="sign")
def sign(value):
    """Produce the signed token used by tokenized order URLs (D-4/FR-15).

    The same Signer verifies tokens in the order-status and checkout-success
    views, so links built in templates and links built in emails are
    interchangeable.
    """
    return Signer().sign(str(value))


@register.filter(name="format_centavos")
def format_centavos_filter(value):
    """Template-safe peso rendering; malformed values render empty, never 500."""
    try:
        return _format_centavos(value)
    except MoneyValueError:
        return ""
