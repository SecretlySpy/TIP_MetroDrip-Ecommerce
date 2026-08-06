"""Draining the transactional outbox, without a broker.

ADR-P3-003 forbids a message broker, and none is needed at this scale. MySQL
8's `SELECT ... FOR UPDATE SKIP LOCKED` lets concurrent drainers claim disjoint
batches without blocking on each other, which is the single feature that makes
a database-backed queue workable here. It also means a second drainer is
*safe*, so the single-scheduler constraint in ADR-A-014 becomes an efficiency
choice rather than a correctness one.

Delivery is at-least-once. Combined with the ledger's idempotency keys
(ADR-P3-016) the observable effect is exactly-once, which is why every handler
below must pass a stable key rather than inventing one per attempt.
"""

import datetime
import logging
import random

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from config.middleware import bind_correlation_id

logger = logging.getLogger(__name__)

#: Give up after this many attempts. At the backoff below that is a bit over an
#: hour of retrying — long enough to ride out a sidecar restart, short enough
#: that a genuinely broken message reaches a human the same working day.
MAX_ATTEMPTS = 8
BACKOFF_CAP_SECONDS = 300

#: topic -> handler(payload) -> None. A handler must raise to signal failure.
_HANDLERS = {}


def register_handler(topic):
    """Register the deliverer for one topic."""

    def decorator(function):
        _HANDLERS[topic] = function
        return function

    return decorator


def enqueue(*, topic, payload, correlation_id=""):
    """Record durable intent. Call inside the transaction that decided it.

    That placement is the whole point: either the business fact and the
    instruction to act on it both commit, or neither does.
    """
    from apps.orders.models import OutboxMessage

    return OutboxMessage.objects.create(
        topic=topic,
        payload=payload,
        correlation_id=correlation_id,
        next_attempt_at=timezone.now(),
    )


def _backoff_seconds(attempts):
    """Exponential with jitter, so concurrent retries do not resynchronise."""
    base = min(2**attempts, BACKOFF_CAP_SECONDS)
    return base * (0.5 + random.random())


def drain_outbox(batch_size=50):
    """Deliver one batch of due messages. Returns (delivered, failed).

    Claiming and delivering are deliberately separate: the rows are marked as
    claimed in a short transaction, then delivered outside it. Holding a
    database transaction open across an HTTP call would put network latency
    inside a lock and is how a slow sidecar becomes a stalled database.
    """
    from apps.orders.models import OutboxMessage, OutboxState

    with transaction.atomic():
        claimed = list(
            OutboxMessage.objects.select_for_update(skip_locked=True)
            .filter(state=OutboxState.PENDING, next_attempt_at__lte=timezone.now())
            .order_by("id")[:batch_size]
        )
        if not claimed:
            return 0, 0
        # Bump attempts while the lock is held so a crash mid-delivery still
        # counts as a try — otherwise a message that reliably kills its worker
        # would be retried forever.
        OutboxMessage.objects.filter(pk__in=[row.pk for row in claimed]).update(
            attempts=F("attempts") + 1
        )

    delivered = failed = 0
    for message in claimed:
        with bind_correlation_id(message.correlation_id):
            if _deliver_one(message):
                delivered += 1
            else:
                failed += 1
    return delivered, failed


def _deliver_one(message):
    from apps.orders.models import OutboxMessage, OutboxState

    handler = _HANDLERS.get(message.topic)
    if handler is None:
        logger.error("outbox: no handler registered for topic %s", message.topic)
        OutboxMessage.objects.filter(pk=message.pk).update(
            state=OutboxState.DEAD, last_error=f"no handler for topic {message.topic}"
        )
        return False

    try:
        handler(message.payload or {})
    except Exception as error:
        attempts = message.attempts + 1
        if attempts >= MAX_ATTEMPTS:
            logger.critical(
                "outbox: %s exhausted %d attempts and needs a human: %s",
                message.topic,
                attempts,
                error,
            )
            OutboxMessage.objects.filter(pk=message.pk).update(
                state=OutboxState.DEAD, last_error=str(error)[:2000]
            )
        else:
            logger.warning("outbox: %s attempt %d failed: %s", message.topic, attempts, error)
            OutboxMessage.objects.filter(pk=message.pk).update(
                next_attempt_at=timezone.now()
                + datetime.timedelta(seconds=_backoff_seconds(attempts)),
                last_error=str(error)[:2000],
            )
        return False

    OutboxMessage.objects.filter(pk=message.pk).update(
        state=OutboxState.SENT, sent_at=timezone.now(), last_error=""
    )
    return True
