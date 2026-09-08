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

from django.db import transaction
from django.utils import timezone

from apps.inventory.services import (
    InsufficientStock,
    ReservationUnavailable,
    commit_holds,
    reserve_lines,
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


def _consume_committed_order_holds(order):
    """Commit or replay each receipt after the payment has committed.

    Catalog owns each stock transaction. Orders records per-hold intent and
    retires it after an idempotent owner response; the outer fulfillment intent
    remains pending if any hold or shortfall is unresolved.
    """
    committed_by_variant: dict[int, int] = {}

    checkout_ids = (
        order.stock_holds.filter(state__in=[StockHoldState.ACTIVE, StockHoldState.COMMITTED])
        .values_list("checkout_id", flat=True)
        .distinct()
    )

    for checkout_id in checkout_ids:
        message = enqueue(
            topic=TOPIC_STOCK_COMMIT,
            payload={
                "checkout_id": checkout_id,
                "order_no": order.order_no,
                "order_id": order.pk,
            },
            correlation_id=get_correlation_id(),
        )

        try:
            result = commit_holds(
                checkout_id=checkout_id,
                order_no=order.order_no,
                order_id=order.pk,
                # This runs with the delivery transaction open, so the remote
                # budget is one tight attempt and the outbox row enqueued above
                # carries the retry (ADR-P3-028).
                inside_transaction=True,
            )
        except ReservationUnavailable:
            logger.exception(
                "Order %s: commit uncertain for hold checkout_id %s", order.order_no, checkout_id
            )
            order.stock_holds.filter(checkout_id=checkout_id, state=StockHoldState.ACTIVE).update(
                state=StockHoldState.UNKNOWN
            )
            continue

        _retire(message)

        for variant_id, qty in (result or {}).items():
            committed_by_variant[variant_id] = committed_by_variant.get(variant_id, 0) + qty

        order.stock_holds.filter(checkout_id=checkout_id, state=StockHoldState.ACTIVE).update(
            state=StockHoldState.COMMITTED, committed_at=timezone.now()
        )

    if not order.stock_holds.filter(state=StockHoldState.UNKNOWN).exists():
        _cover_shortfall(order, committed_by_variant)
    return committed_by_variant


def _cover_shortfall(order, committed_by_variant):
    """Replace expired holds with stable, replayable reservation keys.

    Failure leaves the durable order fulfillment instruction pending. After
    retry exhaustion the operator can refund; no incomplete work is retired.
    """
    for item in order.items.all():
        shortfall = item.qty - committed_by_variant.get(item.variant_id, 0)
        if shortfall <= 0:
            continue
        try:
            replacement_id = f"shortfall-{order.pk}-{item.variant_id}"
            reserve_lines(
                checkout_id=replacement_id,
                lines=[{"variant_id": item.variant_id, "qty": shortfall}],
            )
            commit_holds(
                checkout_id=replacement_id,
                order_no=order.order_no,
                order_id=order.pk,
            )
            committed_by_variant[item.variant_id] = (
                committed_by_variant.get(item.variant_id, 0) + shortfall
            )
        except (InsufficientStock, ReservationUnavailable) as error:
            logger.critical(
                "Order %s PAID but variant %s short by %d units — manual refund needed",
                order.order_no,
                item.variant_id,
                shortfall,
            )
            raise ReservationUnavailable("Paid stock fulfillment remains incomplete") from error


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


TOPIC_ORDER_FULFILL = "order.fulfill_stock"


def consume_order_holds(order):
    """Commit payment and durable stock intent together before contacting Catalog.

    With five connections a Catalog commit cannot roll back with Orders. Never
    consume stock until the payment transaction commits. A crash in this window
    leaves the persisted outbox instruction for the scheduler.
    """
    message = enqueue(topic=TOPIC_ORDER_FULFILL, payload={"order_id": order.pk})

    def attempt():
        try:
            deliver_order_stock(message.payload)
        except Exception:
            logger.exception("Deferred stock fulfillment for order %s", order.pk)
        else:
            _retire(message)

    transaction.on_commit(attempt, using=order._state.db, robust=True)
    return {}


@register_handler(TOPIC_ORDER_FULFILL)
def deliver_order_stock(payload):
    from apps.orders.models import Order, OrderStatus

    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=payload["order_id"])
        if order.status in (OrderStatus.CANCELLED, OrderStatus.REFUNDED):
            return
        if order.status == OrderStatus.PENDING:
            raise ValueError("Cannot consume inventory for an unpaid order")
        result = _consume_committed_order_holds(order)
        if order.stock_holds.filter(state=StockHoldState.UNKNOWN).exists():
            raise ReservationUnavailable("Stock outcome remains unknown")
        return result
