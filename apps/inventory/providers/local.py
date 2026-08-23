"""In-process inventory provider — the proven Epic B implementation.

Every mutation runs inside transaction.atomic() holding select_for_update() row
locks (Hard Invariant 1). Lock-ordering discipline: whenever both rows are
needed, lock the Reservation BEFORE its StockRecord; reserve_stock locks only
the StockRecord (its reservation row does not exist yet). A single global order
makes lock-cycle deadlocks impossible.
"""

import datetime
import hashlib
import json
import logging
from types import SimpleNamespace

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.inventory.exceptions import (
    InsufficientStock,
    InvalidReservationState,
    InvalidStockAdjustment,
)
from apps.inventory.models import (
    IdempotencyRecord,
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


def _idempotency_key(route, checkout_id):
    """Namespace by route so one checkout_id can guard several operations."""
    return hashlib.sha256(f"{route}:{checkout_id}".encode()).hexdigest()


def _fingerprint(lines):
    """Canonical hash of the requested lines, stable across ordering."""
    payload = sorted(
        ({"variant_id": int(line["variant_id"]), "qty": int(line["qty"])} for line in lines),
        key=lambda item: item["variant_id"],
    )
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _absent_stock_record(variant_id):
    """A variant with no StockRecord reads as zero, never as an error.

    A SKU that was never stocked and a SKU that sold out are the same answer to
    every caller — "you cannot buy this" — and making the former raise would
    turn a merchandising gap into a 500 on a product page.
    """
    return SimpleNamespace(
        variant_id=variant_id,
        qty_on_hand=0,
        qty_reserved=0,
        low_stock_threshold=0,
        available=0,
    )


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

    def reserve_stock(self, *, variant_id, qty, session_key="", order=None, checkout_id=""):
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
                checkout_id=checkout_id,
                expires_at=timezone.now()
                + datetime.timedelta(minutes=settings.RESERVATION_TTL_MINUTES),
            )

    def reserve_lines(self, *, checkout_id, lines, session_key="", ttl_minutes=None):
        """Reserve every line under one `checkout_id`, or reserve nothing.

        All-or-nothing because a partially reserved cart leaves stock held for
        an order the caller is about to abandon. Lines are locked in
        `variant_id` order — one global lock order, so two carts sharing SKUs
        can block but never form a cycle.
        """
        if not checkout_id:
            raise ValueError("checkout_id is required.")
        lines = list(lines)
        if not lines:
            raise ValueError("At least one line is required.")

        ttl = ttl_minutes or settings.RESERVATION_TTL_MINUTES
        expires_at = timezone.now() + datetime.timedelta(minutes=ttl)
        ordered = sorted(lines, key=lambda line: int(line["variant_id"]))

        with transaction.atomic():
            # Replay guard, and it must be a *write* to be one. This was a plain
            # SELECT — which concurrency gate G5 proved is not a guard at all:
            # five simultaneous retries of one checkout_id each saw "nothing
            # reserved yet" and all five proceeded, holding 9 units instead of 3.
            #
            # Claiming a uniquely-keyed row makes the check atomic, because the
            # primary key does the arbitration. The loser blocks until the
            # winner commits, then takes the replay path. Same mechanism the
            # service uses (ADR-P3-016); the local path needs it for the same
            # reason, since a client can have several retries in flight at once.
            try:
                with transaction.atomic():
                    IdempotencyRecord.objects.create(
                        key_hash=_idempotency_key("reserve_lines", checkout_id),
                        request_fingerprint=_fingerprint(ordered),
                        status_code=201,
                    )
            except IntegrityError:
                # Someone else claimed this checkout_id. Their rows are
                # committed by the time the lock released, so a locking read
                # returns them rather than a stale snapshot.
                return list(Reservation.objects.select_for_update().filter(checkout_id=checkout_id))

            created = []
            for line in ordered:
                variant_id = int(line["variant_id"])
                qty = _require_positive_int(int(line["qty"]), "qty")
                stock = StockRecord.objects.select_for_update().get(variant_id=variant_id)
                if stock.available < qty:
                    raise InsufficientStock(
                        f"variant {variant_id}: requested {qty}, available {stock.available}"
                    )
                stock.qty_reserved += qty
                stock.save(update_fields=["qty_reserved"])
                created.append(
                    Reservation.objects.create(
                        variant_id=variant_id,
                        qty=qty,
                        session_key=session_key,
                        checkout_id=checkout_id,
                        expires_at=expires_at,
                    )
                )
            return created

    def commit_holds(self, *, checkout_id, order_no="", order_id=None, inside_transaction=False):
        """Convert every ACTIVE hold in a checkout group into a sale.

        Returns `{variant_id: qty}` for what was actually committed. The paid
        path needs per-variant totals to detect a shortfall (a hold that
        expired before payment landed), and it must get them from the ledger
        rather than by reading reservation rows it does not own.

        An already-committed group returns `{}` rather than raising, so a
        replayed payment webhook is a no-op — the webhook is the only payment
        truth (Invariant 3) and providers retry it.
        """
        committed: dict[int, int] = {}
        reservations = list(
            Reservation.objects.filter(
                checkout_id=checkout_id, status=ReservationStatus.ACTIVE
            ).values_list("pk", "variant_id", "qty")
        )
        for reservation_id, variant_id, qty in reservations:
            try:
                self.commit_reservation(reservation_id=reservation_id, order_id=order_id)
            except InvalidReservationState:
                # Lost a race with the sweep or another commit; the shortfall
                # loop downstream re-reserves whatever is missing.
                logger.warning("reservation %s was not committable", reservation_id)
                continue
            committed[variant_id] = committed.get(variant_id, 0) + qty
        return committed

    def release_holds(self, *, checkout_id):
        """Release every ACTIVE hold in a checkout group; unknown ids are a no-op.

        Compensation runs where the caller cannot know whether a reserve landed,
        so "nothing to release" has to be success rather than an error.
        """
        released = 0
        reservation_ids = list(
            Reservation.objects.filter(
                checkout_id=checkout_id, status=ReservationStatus.ACTIVE
            ).values_list("pk", flat=True)
        )
        for reservation_id in reservation_ids:
            self.release_reservation(reservation_id)
            released += 1
        return released

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

    def commit_reservation(self, *, reservation_id, order=None, order_id=None):
        """Convert an ACTIVE hold into a sale on payment confirmation (D-3).

        Accepts `order_id` as well as `order` because only scalars may cross a
        service boundary; the instance form stays for in-process callers.
        """
        if order_id is None and order is not None:
            order_id = order.pk
        with transaction.atomic():
            reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
            if reservation.status != ReservationStatus.ACTIVE:
                raise InvalidReservationState(
                    f"reservation {reservation_id} is {reservation.status}, not active."
                )

            stock = StockRecord.objects.select_for_update().get(variant_id=reservation.variant_id)
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
                ref_order_id=order_id,
            )

            reservation.status = ReservationStatus.COMMITTED
            reservation.order_id = order_id
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
            return _absent_stock_record(variant_id)

    def get_stock_records(self, variant_ids):
        """Counters for many SKUs in one query; unknown SKUs read as zero."""
        wanted = list(dict.fromkeys(variant_ids))  # de-duplicate, keep order
        found = {
            record.variant_id: record
            for record in StockRecord.objects.filter(variant_id__in=wanted)
        }
        return {
            variant_id: found.get(variant_id) or _absent_stock_record(variant_id)
            for variant_id in wanted
        }
