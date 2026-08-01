"""Simulated payment provider for dev/free-tier deployments (D-08, NFR-16).

Supports all four FR-15 scenarios: success, failure, cancellation, and repeated
callback. The repeated callback MUST NOT create a second payment, order, or
stock deduction (NFR-04 idempotency).
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.inventory.services import (
    InsufficientStock,
    InvalidReservationState,
    commit_reservation,
    reserve_stock,
)
from apps.orders.models import OrderStatus

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

            # Consume stock holds — same logic as production path.
            committed_by_variant = {}
            for reservation in order.reservations.filter(status="active"):
                try:
                    commit_reservation(reservation_id=reservation.pk, order=order)
                    committed_by_variant[reservation.variant_id] = (
                        committed_by_variant.get(reservation.variant_id, 0) + reservation.qty
                    )
                except InvalidReservationState:
                    logger.warning(
                        "Order %s: reservation %s not committable",
                        order.order_no,
                        reservation.pk,
                    )

            for item in order.items.all():
                shortfall = item.qty - committed_by_variant.get(item.variant_id, 0)
                if shortfall <= 0:
                    continue
                try:
                    replacement = reserve_stock(
                        variant_id=item.variant_id, qty=shortfall, order=order
                    )
                    commit_reservation(reservation_id=replacement.pk, order=order)
                except InsufficientStock:
                    logger.critical(
                        "Order %s PAID but variant %s short by %d units — manual refund needed",
                        order.order_no,
                        item.variant_id,
                        shortfall,
                    )

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
