"""Simulated payment provider for dev/free-tier deployments (D-08, NFR-16).

Supports all four FR-15 scenarios: success, failure, cancellation, and repeated
callback. The repeated callback MUST NOT create a second payment, order, or
stock deduction (NFR-04 idempotency).
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.orders.models import OrderStatus
from apps.payments.holds import consume_order_holds

from ..models import Payment, PaymentMethod, PaymentStatus
from . import PaymentProvider, register_provider

logger = logging.getLogger(__name__)


@register_provider("simulated")
class SimulatedPaymentProvider(PaymentProvider):
    """In-process payment simulator that exercises the full checkout flow."""

    def create_checkout_session(self, order, success_url, cancel_url):
        """Create a pending Payment record and return a mock checkout URL."""
        Payment.objects.get_or_create(
            order=order,
            defaults={
                "provider_ref": f"sim_session_{order.order_no}",
                "method": PaymentMethod.CARD,
                "status": PaymentStatus.PENDING,
                "amount": order.total,
            },
        )
        separator = "&" if "?" in success_url else "?"
        return f"{success_url}{separator}mock=1", f"sim_session_{order.order_no}"

    def confirm_order_paid(self, *, order, method=None):
        """Idempotently flip order to Paid and consume stock holds.

        Returns True on first confirmation, False when the payment was
        already processed (replay / repeated callback — NFR-04).
        """
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(order=order)
            if payment.status == PaymentStatus.PAID:
                logger.info(
                    "Simulated replay: order %s already paid — idempotent no-op.",
                    order.order_no,
                )
                return False

            payment.status = PaymentStatus.PAID
            payment.paid_at = timezone.now()
            update_fields = ["status", "paid_at"]
            if method in PaymentMethod.values:
                payment.method = method
                update_fields.append("method")
            payment.save(update_fields=update_fields)

            # Consume stock holds by checkout_id, never by following a reverse
            # FK into the ledger's tables (apps/payments/holds.py).
            consume_order_holds(order)

            order.transition_to(OrderStatus.PAID)
        return True

    def simulate_failure(self, order):
        """FR-15 scenario: mark the payment as failed."""
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(order=order)
            if payment.status != PaymentStatus.PENDING:
                return False
            payment.status = PaymentStatus.FAILED
            payment.save(update_fields=["status"])
            order.transition_to(OrderStatus.CANCELLED)
        return True

    def simulate_cancellation(self, order):
        """FR-15 scenario: buyer cancels before paying."""
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(order=order)
            if payment.status != PaymentStatus.PENDING:
                return False
            payment.status = PaymentStatus.FAILED
            payment.save(update_fields=["status"])
            order.transition_to(OrderStatus.CANCELLED)
        return True
