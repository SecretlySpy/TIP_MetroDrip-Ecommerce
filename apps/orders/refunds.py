"""Durable stock restoration after a committed full-order refund."""

import logging
from types import SimpleNamespace

from django.db import transaction

from apps.orders.outbox import enqueue, register_handler

logger = logging.getLogger(__name__)
TOPIC_REFUND = "order.restore_stock"


def enqueue_refund(order):
    message = enqueue(
        topic=TOPIC_REFUND,
        payload={
            "order_id": order.pk,
            "order_no": order.order_no,
            "lines": list(order.items.values("variant_id", "qty")),
        },
    )

    def attempt():
        from apps.payments.holds import _retire

        try:
            deliver_refund(message.payload)
        except Exception:
            logger.exception("Refund %s committed; stock restoration queued", order.order_no)
        else:
            _retire(message)

    transaction.on_commit(attempt, using=order._state.db, robust=True)


@register_handler(TOPIC_REFUND)
def deliver_refund(payload):
    from apps.inventory.services import restore_order_stock

    restore_order_stock(
        order=SimpleNamespace(pk=payload["order_id"], order_no=payload["order_no"]),
        lines=payload["lines"],
    )
