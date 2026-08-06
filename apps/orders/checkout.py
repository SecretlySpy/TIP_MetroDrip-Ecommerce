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
from apps.inventory.services import ReservationUnavailable, release_holds, reserve_lines
from apps.orders.models import Order, OrderItem, OrderStatus, StockHold, StockHoldState
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


def _release_quietly(checkout_id):
    """Give stock back on a failed checkout. Returns whether it succeeded.

    Compensation must never replace the error that caused it — a caller that
    fails to release should still surface the original failure, not a
    release failure. When this returns False the TTL sweep is the backstop, so
    the cost is bounded at RESERVATION_TTL_MINUTES of under-selling and can
    never become an oversell.

    Releasing an id that was never reserved is a documented no-op, so this is
    safe to call on any failure branch without first establishing what landed.
    """
    try:
        release_holds(checkout_id=checkout_id)
        return True
    except Exception:
        logger.exception("Failed to release holds for checkout %s", checkout_id)
        return False


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

    Stock is secured before the order row exists (ADR-P3-022), so a rejected
    cart leaves nothing behind at all — no order, no line, no burnt order
    number. Every failure after the reserve compensates by releasing the
    `checkout_id`, which is a documented no-op when nothing was held.

    Raises:
        CheckoutError            400-class: bad lines, zone, or contact.
        InsufficientStock        409-class: nothing was written anywhere.
        ReservationUnavailable   502-class: the stock ledger could not be
                                 reached or its answer was uncertain. Held
                                 stock, if any, has been released.
        PaymentSessionError      502-class: the order exists but is unpayable,
                                 so it is cancelled and its holds released.
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

    # --- S0: price the cart. Still no writes anywhere. ---------------------
    variants = {
        variant.pk: variant
        for variant in ProductVariant.objects.select_related("product").filter(pk__in=quantities)
    }
    if set(quantities) - set(variants):
        raise CheckoutError("Some cart items no longer exist — refresh your cart.")

    # Effective price honors variant overrides; totals are computed once here so
    # chk_order_total_reconciles holds from the order's first write.
    subtotal = sum(variants[vid].price * qty for vid, qty in quantities.items())

    # Minted before any write, so it exists while the Order still does not. It
    # is the only identity that crosses to the stock ledger: compensation says
    # "release this checkout_id", never "delete the rows you created for me".
    checkout_id = uuid.uuid4().hex

    # --- S1: secure the stock BEFORE an order row exists -------------------
    #
    # ADR-P3-004 originally specified CreateOrder → ReserveStock. That ordering
    # is the more dangerous one and ADR-P3-022 amends it. Reserving first means
    # a sold-out cart writes *nothing*: no burnt order number (the public
    # format allows only 99,999 a year), no committed `pending` order visible in
    # the merchant console and at /order/<token>/ before its stock is secured,
    # and no window in which a payment webhook could arrive for an order that
    # holds nothing. Deleting such an order is not an option either — the
    # PROTECT edges from StockMovement and Review exist precisely to stop it.
    #
    # InsufficientStock propagates untouched: reserve is all-or-nothing, so
    # there is nothing to compensate.
    try:
        reserve_lines(
            checkout_id=checkout_id,
            lines=[{"variant_id": vid, "qty": qty} for vid, qty in quantities.items()],
            session_key=session_key,
        )
    except ReservationUnavailable:
        # The ledger may or may not be holding stock for this checkout_id.
        # Releasing it is a no-op if it is not, so this is always safe and
        # never depends on knowing which happened.
        #
        # Re-raised as itself rather than folded into PaymentSessionError: both
        # are 502-class, but telling a shopper "the payment provider is down"
        # when the stock service is down sends them to the wrong conclusion and
        # sends an on-call engineer to the wrong system.
        _release_quietly(checkout_id)
        raise

    # --- S2: the order row. Pure Django, so the retry replays only local work ---
    def _build_order():
        with transaction.atomic():
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
                OrderItem.objects.create(
                    order=order,
                    variant=variants[variant_id],
                    qty=qty,
                    unit_price_snapshot=variants[variant_id].price,
                )

            # Orders' own receipt for the stock the ledger is holding. Everything
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
                # Out of retries, or a different database fault. The stock is
                # held and no order will ever claim it, so give it back now
                # rather than leaving it stranded for the full TTL.
                _release_quietly(checkout_id)
                raise
            # The victim's transaction rolled back completely (order number
            # included) — brief backoff, then rebuild. The holds are untouched
            # by that rollback because they were taken before it began, which
            # is the point: the retry replays local work only.
            logger.warning("Checkout deadlock (attempt %d); retrying.", attempt)
            time.sleep(0.05 * attempt)
        except Exception:
            _release_quietly(checkout_id)
            raise

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
        if _release_quietly(checkout_id):
            StockHold.objects.filter(order=order).update(state=StockHoldState.RELEASED)
        else:
            # The TTL sweep is the backstop, so a failed compensation costs at
            # most RESERVATION_TTL_MINUTES of under-selling — never an oversell.
            StockHold.objects.filter(order=order).update(state=StockHoldState.UNKNOWN)

        # The order is unpayable and previously stayed `pending` forever, which
        # left it in the merchant console indefinitely and kept open the window
        # where a late webhook could pay an order holding no stock. Cancelling
        # closes both. A failure here must not mask the original error.
        try:
            order.transition_to(OrderStatus.CANCELLED)
        except Exception:
            logger.exception("Could not cancel unpayable order %s", order.order_no)

        raise PaymentSessionError("Payment provider is unavailable right now.") from error

    return order, checkout_url
