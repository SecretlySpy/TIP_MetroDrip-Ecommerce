"""Consume an order's stock holds when payment is confirmed.

Both payment providers ran a near-identical copy of this. Both iterated
`order.reservations.filter(status="active")` — a reverse foreign key into
`inventory_reservation`. That is correct only while Orders and the stock ledger
share one schema. Against a separate ledger the queryset returns **empty**, the
loop commits nothing, and the shortfall pass below silently re-reserves and
re-commits every line. Net effect: the payment succeeds, `qty_on_hand` never
moves, and no `StockMovement` row is written — Hard Invariant 4 failing
silently on the money path, and untested (ADR-P3-012).

Reading `StockHold` instead keeps the question inside Orders ("what did I ask
the ledger to hold?") and asks the ledger to act by `checkout_id`, which works
whichever side owns the rows.
"""

import logging

from django.utils import timezone

from apps.inventory.services import (
    InsufficientStock,
    ReservationUnavailable,
    commit_holds,
    reserve_stock,
)
from apps.orders.models import StockHoldState

logger = logging.getLogger(__name__)


def consume_order_holds(order):
    """Commit every active hold on `order`, then cover any shortfall.

    Must be called inside the same transaction as the payment status flip, so
    that "paid" and "stock consumed" cannot disagree while both live in one
    database. Once the ledger is remote that atomicity is replaced by an
    outbox row written in this transaction (ADR-P3-004 unlock item, Phase B6).

    Returns `{variant_id: qty}` actually committed.
    """
    committed_by_variant: dict[int, int] = {}

    for hold in order.stock_holds.filter(state=StockHoldState.ACTIVE):
        try:
            result = commit_holds(
                checkout_id=hold.checkout_id,
                order_no=order.order_no,
                order_id=order.pk,
            )
        except ReservationUnavailable:
            # The ledger may or may not have applied it. Leave the hold in
            # `unknown` for reconciliation rather than guessing; the shortfall
            # pass below still protects the customer's order.
            logger.exception(
                "Order %s: commit uncertain for hold %s", order.order_no, hold.checkout_id
            )
            hold.state = StockHoldState.UNKNOWN
            hold.save(update_fields=["state"])
            continue

        for variant_id, qty in (result or {}).items():
            committed_by_variant[variant_id] = committed_by_variant.get(variant_id, 0) + qty

        hold.state = StockHoldState.COMMITTED
        hold.committed_at = timezone.now()
        hold.save(update_fields=["state", "committed_at"])

    _cover_shortfall(order, committed_by_variant)
    return committed_by_variant


def _cover_shortfall(order, committed_by_variant):
    """Re-reserve and commit anything the holds did not cover.

    A hold can expire between checkout and payment confirmation, so the units
    a paid order needs may no longer be held. This is the safety valve for
    that; it is also the last line of defence when a commit came back
    uncertain. When even this fails the order is paid and cannot be fulfilled,
    which is a refund decision for a human — hence CRITICAL.
    """
    for item in order.items.all():
        shortfall = item.qty - committed_by_variant.get(item.variant_id, 0)
        if shortfall <= 0:
            continue
        try:
            replacement_id = f"shortfall-{order.pk}-{item.variant_id}"
            reserve_stock(
                variant_id=item.variant_id,
                qty=shortfall,
                order=order,
                checkout_id=replacement_id,
            )
            commit_holds(
                checkout_id=replacement_id,
                order_no=order.order_no,
                order_id=order.pk,
            )
            committed_by_variant[item.variant_id] = (
                committed_by_variant.get(item.variant_id, 0) + shortfall
            )
        except (InsufficientStock, ReservationUnavailable):
            logger.critical(
                "Order %s PAID but variant %s short by %d units — manual refund needed",
                order.order_no,
                item.variant_id,
                shortfall,
            )
