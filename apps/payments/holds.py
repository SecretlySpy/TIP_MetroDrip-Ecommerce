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
from apps.orders.models import OutboxState, StockHoldState
from apps.orders.outbox import enqueue, register_handler
from config.middleware import get_correlation_id

logger = logging.getLogger(__name__)


def _retire(message):
    """Mark a queued instruction as satisfied by the synchronous attempt."""
    from apps.orders.models import OutboxMessage

    OutboxMessage.objects.filter(pk=message.pk).update(
        state=OutboxState.SENT, sent_at=timezone.now()
    )


TOPIC_STOCK_COMMIT = "stock.commit"


def consume_order_holds(order):
    """Commit every active hold on `order`, then cover any shortfall.

    Called inside the same transaction as the payment status flip. While the
    ledger is in-process that makes "paid" and "stock consumed" atomic. Once it
    is remote they are two systems, so durable intent is recorded first: an
    outbox row committed with the payment (ADR-P3-018). Delivery is then
    at-least-once against the ledger's idempotency keys, which is exactly-once
    in effect.

    The synchronous attempt below is kept because it is what makes stock move
    *immediately* in the common case; the outbox exists for when it does not.

    Returns `{variant_id: qty}` actually committed.
    """
    committed_by_variant: dict[int, int] = {}

    for hold in order.stock_holds.filter(state=StockHoldState.ACTIVE):
        # Written before the attempt and inside the payment transaction, so a
        # crash between the payment flip and the commit call cannot lose the
        # instruction. The poller retries it; the ledger de-duplicates it.
        message = enqueue(
            topic=TOPIC_STOCK_COMMIT,
            payload={
                "checkout_id": hold.checkout_id,
                "order_no": order.order_no,
                "order_id": order.pk,
            },
            correlation_id=get_correlation_id(),
        )

        try:
            result = commit_holds(
                checkout_id=hold.checkout_id,
                order_no=order.order_no,
                order_id=order.pk,
            )
        except ReservationUnavailable:
            # The ledger may or may not have applied it. Leave the hold in
            # `unknown` and let the outbox row drive the retry rather than
            # guessing an outcome here; the shortfall pass below still
            # protects the customer's order in the meantime.
            logger.exception(
                "Order %s: commit uncertain for hold %s", order.order_no, hold.checkout_id
            )
            hold.state = StockHoldState.UNKNOWN
            hold.save(update_fields=["state"])
            continue

        # The synchronous attempt succeeded, so the queued instruction is
        # redundant. Retiring it here keeps the poller's backlog honest.
        _retire(message)

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


@register_handler(TOPIC_STOCK_COMMIT)
def deliver_stock_commit(payload):
    """Outbox handler: retry a stock commit the request could not complete.

    Raising propagates to the poller, which schedules a backoff retry. The
    ledger de-duplicates on `checkout_id`, so re-delivery cannot double-consume
    even if an earlier attempt actually landed and only the reply was lost.
    """
    from apps.orders.models import StockHold, StockHoldState

    checkout_id = payload["checkout_id"]
    commit_holds(
        checkout_id=checkout_id,
        order_no=payload.get("order_no", ""),
        order_id=payload.get("order_id"),
    )
    StockHold.objects.filter(checkout_id=checkout_id).update(
        state=StockHoldState.COMMITTED, committed_at=timezone.now()
    )


def reconcile_unknown_holds(*, limit=100):
    """Resolve holds whose commit outcome the request never learned.

    A hold lands in `unknown` when the ledger returned `ServiceUncertain` — a
    read timeout, or a 5xx after the body was sent. The request could not tell
    "applied" from "not applied", and guessing either way is wrong: assuming
    success loses stock, assuming failure risks selling it twice.

    Asking again is the only correct move, and it is safe precisely because
    `commit_holds` is idempotent on `checkout_id` (ADR-P3-016). If the original
    call did land, the ledger reports nothing left active and the hold is
    simply marked committed; if it did not, this commits it now.

    A hold that stays unknown across sweeps is left alone rather than forced —
    it will keep being retried, and the TTL means the worst case is under-selling
    for the remainder of the reservation window, never an oversell.

    Returns how many were resolved.
    """
    from apps.orders.models import StockHold

    resolved = 0
    stale = StockHold.objects.filter(state=StockHoldState.UNKNOWN).select_related("order")[:limit]
    for hold in stale:
        try:
            commit_holds(
                checkout_id=hold.checkout_id,
                order_no=hold.order.order_no,
                order_id=hold.order_id,
            )
        except ReservationUnavailable:
            logger.warning(
                "Hold %s still unresolved; leaving for the next sweep.", hold.checkout_id
            )
            continue

        hold.state = StockHoldState.COMMITTED
        hold.committed_at = timezone.now()
        hold.save(update_fields=["state", "committed_at"])
        resolved += 1
        logger.info("Hold %s reconciled to committed.", hold.checkout_id)
    return resolved
