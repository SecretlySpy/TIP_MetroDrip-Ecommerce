"""The transactional outbox: durable intent for work a request could not finish.

Why this exists (ADR-P3-018). `confirm_order_paid` flips `Payment.status` and
consumes stock in one transaction, so today the two cannot disagree. Once the
ledger is a separate service they are two systems: a commit call that fails
after the payment row commits means money taken and stock never decremented.
Writing the instruction inside the payment transaction restores atomicity of
*intent*, and at-least-once delivery against the ledger's idempotency keys
gives exactly-once effect.
"""

import datetime

import pytest
from django.utils import timezone

from apps.orders import outbox
from apps.orders.models import OutboxMessage, OutboxState


@pytest.fixture
def topic_registry():
    """Restore the handler registry so tests cannot leak into each other."""
    original = dict(outbox._HANDLERS)
    yield outbox._HANDLERS
    outbox._HANDLERS.clear()
    outbox._HANDLERS.update(original)


@pytest.mark.django_db
def test_delivered_message_is_marked_sent(topic_registry):
    seen = []
    topic_registry["test.ok"] = seen.append
    outbox.enqueue(topic="test.ok", payload={"n": 1}, correlation_id="cid-1")

    delivered, failed = outbox.drain_outbox()

    assert (delivered, failed) == (1, 0)
    assert seen == [{"n": 1}]
    message = OutboxMessage.objects.get()
    assert message.state == OutboxState.SENT
    assert message.sent_at is not None


@pytest.mark.django_db
def test_failed_delivery_is_retried_later_not_dropped(topic_registry):
    """A transient failure must stay pending with a future attempt time."""

    def explode(payload):
        raise RuntimeError("ledger unreachable")

    topic_registry["test.flaky"] = explode
    outbox.enqueue(topic="test.flaky", payload={})

    delivered, failed = outbox.drain_outbox()

    assert (delivered, failed) == (0, 1)
    message = OutboxMessage.objects.get()
    assert message.state == OutboxState.PENDING
    assert message.attempts == 1
    assert message.next_attempt_at > timezone.now()
    assert "unreachable" in message.last_error


@pytest.mark.django_db
def test_a_message_not_yet_due_is_left_alone(topic_registry):
    topic_registry["test.later"] = lambda payload: None
    message = outbox.enqueue(topic="test.later", payload={})
    OutboxMessage.objects.filter(pk=message.pk).update(
        next_attempt_at=timezone.now() + datetime.timedelta(minutes=5)
    )

    assert outbox.drain_outbox() == (0, 0)
    assert OutboxMessage.objects.get().state == OutboxState.PENDING


@pytest.mark.django_db
def test_exhausted_retries_become_dead_rather_than_looping_forever(topic_registry):
    """A permanently broken message must reach a human, not spin."""

    def explode(payload):
        raise RuntimeError("permanently broken")

    topic_registry["test.doomed"] = explode
    message = outbox.enqueue(topic="test.doomed", payload={})
    OutboxMessage.objects.filter(pk=message.pk).update(attempts=outbox.MAX_ATTEMPTS - 1)

    outbox.drain_outbox()

    assert OutboxMessage.objects.get().state == OutboxState.DEAD


@pytest.mark.django_db
def test_unknown_topic_is_dead_lettered_not_retried(topic_registry):
    """Retrying a message nothing can handle would never converge."""
    outbox.enqueue(topic="test.nobody-handles-this", payload={})

    delivered, failed = outbox.drain_outbox()

    assert (delivered, failed) == (0, 1)
    message = OutboxMessage.objects.get()
    assert message.state == OutboxState.DEAD
    assert "no handler" in message.last_error


@pytest.mark.django_db
def test_paid_order_enqueues_and_retires_its_stock_commit(client):
    """The happy path still moves stock synchronously and leaves no backlog."""
    from django.test import override_settings

    from apps.orders.checkout import place_order
    from apps.payments.services import confirm_order_paid
    from tests.test_stock_holds import _variant, _zone

    with override_settings(PAYMENT_PROVIDER="simulated"):
        variant = _variant(sku="OUTBOX-PAID", qty_on_hand=10)
        order, _ = place_order(
            items=[{"variant_id": variant.pk, "qty": 2}],
            zone_id=_zone().pk,
            contact={"name": "Ada", "email": "ada@example.test"},
            success_url="https://example.test/ok",
            cancel_url="https://example.test/no",
        )
        assert confirm_order_paid(order=order) is True

    message = OutboxMessage.objects.get(topic="stock.commit")
    # Recorded inside the payment transaction, then retired because the
    # synchronous commit succeeded — so the poller has nothing left to do.
    assert message.state == OutboxState.SENT
    assert message.payload["order_no"] == order.order_no
    assert OutboxMessage.objects.filter(state=OutboxState.PENDING).count() == 0
