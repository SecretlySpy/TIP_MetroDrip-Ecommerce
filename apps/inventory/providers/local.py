"""In-process inventory provider — the proven Epic B implementation.

Every mutation runs inside transaction.atomic() holding select_for_update() row
locks (Hard Invariant 1). Lock-ordering discipline: whenever both rows are
needed, lock the Reservation BEFORE its StockRecord; reserve_stock locks only
the StockRecord (its reservation row does not exist yet). A single global order
makes lock-cycle deadlocks impossible.
"""

import datetime
import logging
from types import SimpleNamespace

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.inventory.exceptions import (
    InsufficientStock,
    InvalidReservationState,
    InvalidStockAdjustment,
)
from apps.inventory.models import (
    MovementReason,
    Reservation,
    ReservationStatus,
    StockMovement,
    StockRecord,
)

from . import InventoryProvider

logger = logging.getLogger(__name__)


def _require_positive_int(value, name):
    """Reject Booleans and non-integers explicitly — same strictness as money.py."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be an integer of at least 1.")
    return value


def _end_active_reservation(reservation, terminal_status):
    """Return an ACTIVE reservation's units to availability (lock already held)."""
    stock = StockRecord.objects.select_for_update().get(variant_id=reservation.variant_id)
    if stock.qty_reserved < reservation.qty:
        # Counters can only underflow if some code path bypassed this module;
        # fail loudly rather than storing a negative-by-wraparound value.
        raise InvalidReservationState(
            f"reservation {reservation.pk}: qty_reserved underflow on {terminal_status}"
        )
    stock.qty_reserved -= reservation.qty
    stock.save(update_fields=["qty_reserved"])

    reservation.status = terminal_status
    reservation.ended_at = timezone.now()
    reservation.save(update_fields=["status", "ended_at"])
    return reservation


class LocalInventoryProvider(InventoryProvider):
    """Monolith implementation: the only writer of stock counters and movements."""

    def reserve_stock(self, *, variant_id, qty, session_key="", order=None):
        """Place a TTL-bound hold on `qty` units of one SKU (B-1/B-2, FR-5)."""
        _require_positive_int(qty, "qty")

        with transaction.atomic():
            # The row lock serializes competing buyers; both concurrency gates
            # (2 buyers/1 unit and 20 buyers/10 units) prove exactly-N successes.
            stock = StockRecord.objects.select_for_update().get(variant_id=variant_id)
            if stock.available < qty:
                raise InsufficientStock(
                    f"variant {variant_id}: requested {qty}, available {stock.available}"
                )
            stock.qty_reserved += qty
            stock.save(update_fields=["qty_reserved"])

            # Created while the stock lock is held, so hold and counter can
            # never disagree. No StockMovement: holds don't change qty_on_hand.
            return Reservation.objects.create(
                variant_id=variant_id,
                qty=qty,
                session_key=session_key,
                order=order,
                expires_at=timezone.now()
                + datetime.timedelta(minutes=settings.RESERVATION_TTL_MINUTES),
            )

    def release_reservation(self, reservation_id):
        """Give an abandoned/cancelled hold back to availability (idempotent)."""
        with transaction.atomic():
            reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
            if reservation.status in (ReservationStatus.RELEASED, ReservationStatus.EXPIRED):
                return reservation
            if reservation.status == ReservationStatus.COMMITTED:
                raise InvalidReservationState(
                    f"reservation {reservation_id} is committed; a sale cannot be released."
                )
            return _end_active_reservation(reservation, ReservationStatus.RELEASED)

    def commit_reservation(self, *, reservation_id, order):
        """Convert an ACTIVE hold into a sale on payment confirmation (D-3)."""
        with transaction.atomic():
            reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
            if reservation.status != ReservationStatus.ACTIVE:
                raise InvalidReservationState(
                    f"reservation {reservation_id} is {reservation.status}, not active."
                )

            stock = StockRecord.objects.select_for_update().get(
                variant_id=reservation.variant_id
            )
            if stock.qty_on_hand < reservation.qty or stock.qty_reserved < reservation.qty:
                raise InvalidReservationState(
                    f"reservation {reservation_id}: counters cannot cover the committed sale."
                )
            stock.qty_on_hand -= reservation.qty
            stock.qty_reserved -= reservation.qty
            stock.save(update_fields=["qty_on_hand", "qty_reserved"])

            StockMovement.objects.create(
                variant_id=reservation.variant_id,
                delta=-reservation.qty,
                reason=MovementReason.SALE,
                ref_order=order,
            )

            reservation.status = ReservationStatus.COMMITTED
            reservation.order = order
            reservation.ended_at = timezone.now()
            reservation.save(update_fields=["status", "order", "ended_at"])
            return reservation

    def adjust_stock(self, *, variant_id, delta, reason, ref_order=None):
        """Apply a non-sale physical stock change with its audit row (B-1/B-3)."""
        if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0:
            raise InvalidStockAdjustment("delta must be a nonzero integer.")
        reason = MovementReason(reason)
        if reason == MovementReason.SALE:
            raise InvalidStockAdjustment("Sales are recorded via commit_reservation only.")
        if reason in (MovementReason.RESTOCK, MovementReason.RETURN) and delta < 0:
            raise InvalidStockAdjustment(f"{reason} requires a positive delta.")

        with transaction.atomic():
            stock = StockRecord.objects.select_for_update().get(variant_id=variant_id)
            new_on_hand = stock.qty_on_hand + delta
            if new_on_hand < stock.qty_reserved:
                raise InvalidStockAdjustment(
                    f"variant {variant_id}: on-hand {new_on_hand} would drop below "
                    f"reserved {stock.qty_reserved}."
                )
            stock.qty_on_hand = new_on_hand
            stock.save(update_fields=["qty_on_hand"])

            # Ledger row in the same transaction (Invariant 4).
            StockMovement.objects.create(
                variant_id=variant_id, delta=delta, reason=reason, ref_order=ref_order
            )
        return stock

    def release_expired_reservations(self, now=None):
        """TTL sweep: expire every overdue ACTIVE hold; returns how many."""
        if now is None:
            now = timezone.now()

        candidate_ids = list(
            Reservation.objects.filter(
                status=ReservationStatus.ACTIVE, expires_at__lte=now
            ).values_list("pk", flat=True)
        )

        expired_count = 0
        for reservation_id in candidate_ids:
            try:
                with transaction.atomic():
                    reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
                    # Re-check under lock: a commit/release may have won the race.
                    if (
                        reservation.status != ReservationStatus.ACTIVE
                        or reservation.expires_at > now
                    ):
                        continue
                    _end_active_reservation(reservation, ReservationStatus.EXPIRED)
                    expired_count += 1
            except Exception:
                # Log-and-continue: the next sweep retries this row.
                logger.exception("Failed to expire reservation %s", reservation_id)
        return expired_count

    def scan_low_stock(self):
        """StockRecords at/below their threshold on availability (B-4, FR-9)."""
        return (
            StockRecord.objects.annotate(
                available_units=models.F("qty_on_hand") - models.F("qty_reserved")
            )
            .filter(available_units__lte=models.F("low_stock_threshold"))
            .select_related("variant", "variant__product")
            .order_by("variant__sku")
        )

    def get_stock_record(self, variant_id):
        """Current counters for one SKU; unknown SKUs read as zero availability."""
        try:
            return StockRecord.objects.get(variant_id=variant_id)
        except StockRecord.DoesNotExist:
            return SimpleNamespace(
                variant_id=variant_id,
                qty_on_hand=0,
                qty_reserved=0,
                low_stock_threshold=0,
                available=0,
            )
