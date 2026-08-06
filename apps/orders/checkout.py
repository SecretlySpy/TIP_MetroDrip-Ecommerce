"""Canonical checkout service (D-1/H-4): one flow for web and mobile clients.

The client — any client — sends only intent: variant ids, quantities, contact
details, and a zone. Prices, totals, and stock decisions are computed here
(D-13: no business logic on devices). All-or-nothing: any failure inside the
atomic block leaves no order, line, hold, or counter change behind.
"""

import datetime
import logging
import time
import uuid

from django.conf import settings
from django.db import OperationalError, transaction
from django.utils import timezone

from apps.catalog.models import ProductVariant
from apps.inventory.services import release_holds, reserve_stock
from apps.orders.models import Order, OrderItem, StockHold, StockHoldState
from apps.orders.services import next_order_no
from apps.payments.services import create_checkout_session
from apps.shipping.models import ShippingZone

logger = logging.getLogger(__name__)

MAX_CHECKOUT_LINES = 20
MAX_LINE_QTY = 99

# MySQL error 1213: two checkouts chose each other as deadlock victims. The
# transaction fully rolled back, so re-running it is safe and expected practice.
_MYSQL_DEADLOCK = 1213
_DEADLOCK_ATTEMPTS = 3


class CheckoutError(ValueError):
    """Client-correctable checkout rejection (bad lines, zone, contact)."""


class PaymentSessionError(Exception):
    """The payment provider could not produce a session; holds were released."""


def parse_items(raw_items):
    """Validate cart lines and merge duplicate variants; returns {variant_id: qty}."""
    if not isinstance(raw_items, list) or not raw_items:
        raise CheckoutError("Cart is empty.")
    if len(raw_items) > MAX_CHECKOUT_LINES:
        raise CheckoutError(f"A single order supports up to {MAX_CHECKOUT_LINES} lines.")

    quantities = {}
    for line in raw_items:
        try:
            variant_id = int(line["variant_id"])
            qty = int(line["qty"])
        except (KeyError, TypeError, ValueError):
            raise CheckoutError("Each cart line needs a variant_id and qty.") from None
        if not 1 <= qty <= MAX_LINE_QTY:
            raise CheckoutError(f"Quantities must be between 1 and {MAX_LINE_QTY}.")
        quantities[variant_id] = quantities.get(variant_id, 0) + qty
    return quantities


def place_order(
    *,
    items,
    zone_id,
    contact,
    customer=None,
    session_key="",
    success_url,
    cancel_url,
):
    """Create the order with its holds and a payment session; returns (order, checkout_url).

    Raises CheckoutError (400-class), InsufficientStock (409-class), or
    PaymentSessionError (502-class, holds already released).
    """
    quantities = parse_items(items)

    name = str(contact.get("name", "")).strip()
    email = str(contact.get("email", "")).strip()
    if not name or not email:
        raise CheckoutError("Name and email are required.")

    try:
        zone = ShippingZone.objects.get(id=zone_id, is_active=True)
    except (ShippingZone.DoesNotExist, ValueError, TypeError):
        raise CheckoutError("Choose a valid shipping zone.") from None

    # Minted before any write, so it exists while the Order still does not. It
    # is the only identity that crosses to the stock ledger: compensation says
    # "release this checkout_id", never "delete the rows you created for me".
    checkout_id = uuid.uuid4().hex

    def _build_order():
        with transaction.atomic():
            variants = {
                variant.pk: variant
                for variant in ProductVariant.objects.select_related("product").filter(
                    pk__in=quantities
                )
            }
            if set(quantities) - set(variants):
                raise CheckoutError("Some cart items no longer exist — refresh your cart.")

            # Effective price honors variant overrides; totals are correct at
            # INSERT so chk_order_total_reconciles holds from the first write.
            subtotal = sum(variants[vid].price * qty for vid, qty in quantities.items())
            order = Order.objects.create(
                order_no=next_order_no(),
                customer=customer,
                subtotal=subtotal,
                shipping_fee=zone.fee,
                total=subtotal + zone.fee,
                shipping_address={
                    "name": name,
                    "email": email,
                    "phone": str(contact.get("phone", "")).strip(),
                    "address_line1": str(contact.get("address_line1", "")).strip(),
                    "city": str(contact.get("city", "")).strip(),
                    "zone": zone.name,
                },
            )
            for variant_id, qty in quantities.items():
                # Raising here rolls back everything — no half-built orders.
                reserve_stock(
                    variant_id=variant_id,
                    qty=qty,
                    session_key=session_key,
                    order=order,
                    checkout_id=checkout_id,
                )
                OrderItem.objects.create(
                    order=order,
                    variant=variants[variant_id],
                    qty=qty,
                    unit_price_snapshot=variants[variant_id].price,
                )

            # Orders' own receipt for the stock it is holding. Everything
            # downstream — the payment commit, compensation, reconciliation —
            # reads this instead of following a reverse FK into the ledger's
            # tables, which returns empty the moment the ledger is a separate
            # service and silently commits nothing (ADR-P3-012).
            StockHold.objects.create(
                order=order,
                checkout_id=checkout_id,
                expires_at=timezone.now()
                + datetime.timedelta(minutes=settings.RESERVATION_TTL_MINUTES),
            )
            return order

    order = None
    for attempt in range(1, _DEADLOCK_ATTEMPTS + 1):
        try:
            order = _build_order()
            break
        except OperationalError as error:
            deadlocked = error.args and error.args[0] == _MYSQL_DEADLOCK
            if not deadlocked or attempt == _DEADLOCK_ATTEMPTS:
                raise
            # The victim's transaction rolled back completely (order number
            # included) — brief backoff, then rebuild from scratch.
            logger.warning("Checkout deadlock (attempt %d); retrying.", attempt)
            time.sleep(0.05 * attempt)

    # Mobile deep links need the signed status token inside the redirect URL,
    # but the token needs the order id — substitute after the order exists.
    if "__TOKEN__" in success_url or "__TOKEN__" in cancel_url:
        from django.core.signing import Signer

        token = Signer().sign(str(order.pk))
        success_url = success_url.replace("__TOKEN__", token)
        cancel_url = cancel_url.replace("__TOKEN__", token)

    try:
        checkout_url, _ = create_checkout_session(order, success_url, cancel_url)
    except Exception as error:
        # The order committed but no payment session exists: free the holds now
        # instead of stranding them for the 15-minute TTL. Releasing by
        # checkout_id works whichever side owns the ledger, and is a no-op if
        # nothing was ever reserved.
        logger.error("Checkout session failed for %s: %s", order.order_no, error)
        try:
            release_holds(checkout_id=checkout_id)
            StockHold.objects.filter(order=order).update(state=StockHoldState.RELEASED)
        except Exception:
            # The TTL sweep is the backstop, so a failed compensation costs at
            # most RESERVATION_TTL_MINUTES of under-selling — never an oversell.
            logger.exception("Failed to release holds for %s", order.order_no)
            StockHold.objects.filter(order=order).update(state=StockHoldState.UNKNOWN)
        raise PaymentSessionError("Payment provider is unavailable right now.") from error

    return order, checkout_url
