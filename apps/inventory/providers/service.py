"""HTTP client for the stock ledger (`INVENTORY_PROVIDER=service`).

Implements the full inventory contract over versioned sync REST: batch reads,
all-or-nothing reserve, commit and release by `checkout_id`, adjustments, the
TTL sweep, and the low-stock scan. Every mutation carries an idempotency key,
so a retry after an uncertain outcome cannot double-apply (ADR-P3-016).

Three things this deliberately does **not** do, each because an earlier version
did and it caused a revert (ADR-P3-002, ADR-P3-012):

* it never writes Django's tables — the ledger owns its rows, and the order
  link lives on Orders' own `StockHold`;
* it never returns a Django model, only scalars and read-only shapes;
* it never silently degrades a mutation to a no-op. `adjust_stock` used to
  raise, the sweep used to return 0, and the scan used to return `[]`, which
  meant abandoned holds never expired and low-stock alerting stopped without
  a single error.

Still opt-in: `prod.py` pins `INVENTORY_PROVIDER` to `local` until the cutover
criteria in ADR-P3-021 are met.
"""

import hashlib
import json
import logging
import uuid
from types import SimpleNamespace

from django.conf import settings

from apps.core.http import CallPolicy, ServiceCallError, ServiceRejected, call
from apps.inventory.exceptions import (
    InsufficientStock,
    InvalidStockAdjustment,
    ReservationUnavailable,
)
from contracts.inventory_v1 import (
    ROUTE_ADJUSTMENTS,
    ROUTE_COMMIT,
    ROUTE_RELEASE,
    ROUTE_RESERVATIONS,
    ROUTE_STOCK_BATCH,
    ROUTE_STOCK_LOW,
    ROUTE_SWEEP,
    AdjustRequest,
    AdjustResponse,
    CommitRequest,
    CommitResponse,
    LowStockResponse,
    ReleaseResponse,
    ReserveRequest,
    ReserveResponse,
    StockBatchRequest,
    StockBatchResponse,
    SweepResponse,
)

from . import InventoryProvider

logger = logging.getLogger(__name__)


# Reads are safe to retry and sit on the request's critical path, so the budget
# is small and the breaker trips quickly — a slow inventory service must not
# become a slow product page.
_READ_POLICY = CallPolicy(
    connect_timeout=0.5,
    read_timeout=2.0,
    attempts=1,
    breaker_key="inventory.read",
)

# Writes may be retried *because* every one of them carries an idempotency key
# (contracts/inventory_v1.py). Without the key `call()` refuses attempts > 1,
# which is the guard that stops a network blip becoming a double reservation.
_WRITE_POLICY = CallPolicy(
    connect_timeout=1.0,
    read_timeout=5.0,
    attempts=3,
    breaker_key="inventory.write",
)

# The commit that runs *inside the payment transaction* (ADR-P3-028).
#
# `_WRITE_POLICY` costs up to 3 × (1s + 5s) ≈ 18s of wall clock, and on this one
# path every second of it is spent holding a row lock on `Payment` — ADR-P3-018
# already names that shape ("network latency inside a row lock is how a slow
# sidecar becomes a stalled database") but the commit path was still using it.
#
# Retrying here buys nothing, which is what makes cutting it safe rather than a
# trade: `consume_order_holds` writes an outbox row in the same transaction
# before it ever calls, so a failure is already durable intent. The drainer then
# retries with the full budget *outside* any transaction, which is exactly where
# ADR-P3-018 says retries belong. One tight attempt, then let the outbox do its
# job: worst case falls from ~18s to ~3s, and the only thing lost on a timeout is
# the immediacy of the common case, never the commit itself.
_IN_TXN_WRITE_POLICY = CallPolicy(
    connect_timeout=1.0,
    read_timeout=2.0,
    attempts=1,
    # Deliberately the same breaker as _WRITE_POLICY: a ledger that is failing
    # should trip once for every caller, not keep a separate tally per path.
    breaker_key="inventory.write",
)


def _base_url() -> str:
    """Resolve from settings, not module-level os.environ.

    This was read once at import into `INVENTORY_SERVICE_URL`, which put it out
    of reach of `override_settings` and pinned it to Django's *own* port 8000
    while Compose published the service on 8001 — the two disagreed and CI
    papered over it by starting the sidecar on 8000.
    """
    return (getattr(settings, "INVENTORY_SERVICE_URL", "") or "").rstrip("/")


def _service_token() -> str:
    return getattr(settings, "INVENTORY_SERVICE_TOKEN", "") or ""


class DummyReservation:
    """Read-only handle for a reservation the ledger owns.

    Deliberately not a Django model: the row lives in the ledger, and anything
    that looked like one would invite the write-back this provider used to do.
    """

    def __init__(self, pk, *, variant_id=None, qty=None):
        self.pk = pk
        self.id = pk
        self.variant_id = variant_id
        self.qty = qty


class DummyStockRecord:
    def __init__(self, data):
        self.variant_id = data.get("variant_id")
        self.qty_on_hand = data.get("qty_on_hand", 0)
        self.qty_reserved = data.get("qty_reserved", 0)
        self.low_stock_threshold = data.get("low_stock_threshold", 5)
        self.available = data.get("available", 0)


class _LowStockRow:
    """Duck-types the fields `send_low_stock_alert` reads off a StockRecord."""

    def __init__(self, item):
        self.variant_id = item.variant_id
        self.available = item.available
        self.low_stock_threshold = item.low_stock_threshold
        self.qty_on_hand = 0
        self.qty_reserved = 0
        self.variant = SimpleNamespace(
            pk=item.variant_id,
            sku=item.sku,
            product=SimpleNamespace(name=item.product_name),
        )


class ServiceInventoryProvider(InventoryProvider):
    """HTTP client for the inventory ledger. Owns no stock state of its own."""

    def reserve_stock(self, *, variant_id, qty, session_key="", order=None, checkout_id=""):
        """Single-line convenience over `reserve_lines`."""
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an integer of at least 1.")
        checkout_id = checkout_id or uuid.uuid4().hex
        created = self.reserve_lines(
            checkout_id=checkout_id,
            lines=[{"variant_id": variant_id, "qty": qty}],
            session_key=session_key,
        )
        return created[0] if created else None

    def reserve_lines(self, *, checkout_id, lines, session_key="", ttl_minutes=None):
        """Reserve a whole cart in one authenticated, idempotent call.

        The previous implementation posted one line at a time and then wrote the
        returned reservation id back into Django's own `inventory_reservation`
        table to attach the order. That only ever worked because both sides were
        secretly pointed at the same schema (ADR-P3-012); against a real second
        ledger it silently wrote nothing. Nothing here touches Django's tables —
        the order link is carried by `StockHold` on the Orders side instead.
        """
        if not checkout_id:
            raise ValueError("checkout_id is required.")
        payload = ReserveRequest(
            checkout_id=checkout_id,
            lines=[
                {"variant_id": int(item["variant_id"]), "qty": int(item["qty"])} for item in lines
            ],
            session_key=session_key,
            ttl_minutes=ttl_minutes,
        )
        try:
            data = call(
                "POST",
                f"{_base_url()}{ROUTE_RESERVATIONS}",
                policy=_WRITE_POLICY,
                json=payload.model_dump(),
                service_token=_service_token(),
                token_setting_name="INVENTORY_SERVICE_TOKEN",
                idempotency_key=checkout_id,
            )
        except ServiceRejected as error:
            if error.code == "insufficient_stock":
                raise InsufficientStock(error.message or "insufficient stock") from None
            raise ValueError(f"inventory service rejected reserve: {error}") from None
        except ServiceCallError as error:
            # Includes ServiceUncertain: the ledger may hold stock for this
            # checkout_id. The caller compensates by releasing that id, which is
            # a safe no-op if nothing was ever reserved.
            raise ReservationUnavailable(str(error)) from error

        parsed = ReserveResponse.model_validate(data)
        return [
            DummyReservation(row.id, variant_id=row.variant_id, qty=row.qty)
            for row in parsed.reservations
        ]

    def commit_holds(self, *, checkout_id, order_no="", order_id=None, inside_transaction=False):
        """Turn the group's holds into sales. Idempotent on the service side.

        `inside_transaction` selects the tight single-attempt budget described at
        `_IN_TXN_WRITE_POLICY`. Callers holding a database transaction open must
        pass it; the outbox drainer and the reconciliation sweep must not, since
        they are the retry path and run with no transaction held.
        """
        try:
            data = call(
                "POST",
                f"{_base_url()}{ROUTE_COMMIT.format(checkout_id=checkout_id)}",
                policy=_IN_TXN_WRITE_POLICY if inside_transaction else _WRITE_POLICY,
                json=CommitRequest(order_no=order_no or "").model_dump(),
                service_token=_service_token(),
                token_setting_name="INVENTORY_SERVICE_TOKEN",
                idempotency_key=f"{checkout_id}:commit",
            )
        except ServiceCallError as error:
            raise ReservationUnavailable(str(error)) from error
        parsed = CommitResponse.model_validate(data)
        committed: dict[int, int] = {}
        for row in parsed.lines:
            committed[row.variant_id] = committed.get(row.variant_id, 0) + row.qty
        return committed

    def release_holds(self, *, checkout_id):
        """Compensation. A release for an unknown checkout_id is success."""
        try:
            data = call(
                "POST",
                f"{_base_url()}{ROUTE_RELEASE.format(checkout_id=checkout_id)}",
                policy=_WRITE_POLICY,
                json={},
                service_token=_service_token(),
                token_setting_name="INVENTORY_SERVICE_TOKEN",
                idempotency_key=f"{checkout_id}:release",
            )
        except ServiceCallError as error:
            raise ReservationUnavailable(str(error)) from error
        return ReleaseResponse.model_validate(data).released

    def release_reservation(self, reservation_id):
        raise InvalidStockAdjustment(
            "The service ledger releases by checkout_id, not by reservation id; "
            "use release_holds(checkout_id=...)."
        )

    def commit_reservation(self, *, reservation_id, order=None, order_id=None):
        raise InvalidStockAdjustment(
            "The service ledger commits by checkout_id, not by reservation id; "
            "use commit_holds(checkout_id=...)."
        )

    def adjust_stock(self, *, variant_id, delta, reason, ref_order=None, ref_order_no=""):
        """Apply a non-sale physical stock change through the ledger.

        Previously raised outright, which meant a merchant could not restock at
        all under this provider — one of the gaps ADR-P3-002 reverted over.
        """
        if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0:
            raise InvalidStockAdjustment("delta must be a nonzero integer.")

        order_no = ref_order_no or (getattr(ref_order, "order_no", "") if ref_order else "")
        payload = AdjustRequest(
            variant_id=variant_id,
            delta=delta,
            reason=str(reason),
            ref_order_no=order_no,
        )
        # The key is derived from the request itself: an adjustment has no
        # natural client-side id, and a retry of the *same* adjustment must not
        # apply twice while a genuinely new one must not be mistaken for a replay.
        key = hashlib.sha256(json.dumps(payload.model_dump(), sort_keys=True).encode()).hexdigest()
        try:
            data = call(
                "POST",
                f"{_base_url()}{ROUTE_ADJUSTMENTS}",
                policy=_WRITE_POLICY,
                json=payload.model_dump(),
                service_token=_service_token(),
                token_setting_name="INVENTORY_SERVICE_TOKEN",
                idempotency_key=key,
            )
        except ServiceRejected as error:
            raise InvalidStockAdjustment(error.message or str(error)) from None
        except ServiceCallError as error:
            raise ReservationUnavailable(str(error)) from error
        return DummyStockRecord(AdjustResponse.model_validate(data).model_dump())

    def release_expired_reservations(self, now=None):
        """Drive the ledger's TTL sweep.

        This used to return 0 unconditionally with a comment claiming the
        service ran its own sweep. It does not — nothing scheduled one — so
        abandoned holds would never expire and their stock would be lost until
        someone noticed. The scheduler still owns the cadence; the ledger owns
        the transaction.
        """
        try:
            data = call(
                "POST",
                f"{_base_url()}{ROUTE_SWEEP}",
                policy=_WRITE_POLICY,
                json={},
                service_token=_service_token(),
                token_setting_name="INVENTORY_SERVICE_TOKEN",
                idempotency_key=f"sweep:{uuid.uuid4().hex}",
            )
        except ServiceCallError as error:
            # Log and report nothing swept; the next tick retries. Raising here
            # would take down the whole scheduler job.
            logger.warning("inventory sweep unavailable: %s", error)
            return 0
        return SweepResponse.model_validate(data).expired

    def scan_low_stock(self):
        """SKUs at or below threshold, shaped like the in-process result.

        Returns objects exposing `.variant.sku` and `.variant.product.name`
        because that is what `send_low_stock_alert` renders. Without it the
        alert email silently degrades from SKUs to bare integers the moment
        this provider is selected — a parity break invisible to any test that
        only ever exercised the local provider.
        """
        try:
            data = call(
                "GET",
                f"{_base_url()}{ROUTE_STOCK_LOW}",
                policy=_READ_POLICY,
                service_token=_service_token(),
                token_setting_name="INVENTORY_SERVICE_TOKEN",
            )
        except ServiceCallError as error:
            logger.warning("inventory low-stock scan unavailable: %s", error)
            return []
        return [_LowStockRow(item) for item in LowStockResponse.model_validate(data).items]

    def get_stock_record(self, variant_id):
        return self.get_stock_records([variant_id])[variant_id]

    def get_stock_records(self, variant_ids):
        """One round trip for the whole set; unreachable service reads as zero.

        Reading as sold-out on failure is deliberate and asymmetric: it can
        under-sell for the duration of an outage, but it can never oversell.
        """
        wanted = list(dict.fromkeys(variant_ids))
        if not wanted:
            return {}

        records = {}
        try:
            data = call(
                "POST",
                f"{_base_url()}{ROUTE_STOCK_BATCH}",
                policy=_READ_POLICY,
                json=StockBatchRequest(variant_ids=wanted).model_dump(),
                service_token=_service_token(),
                token_setting_name="INVENTORY_SERVICE_TOKEN",
            )
            for row in StockBatchResponse.model_validate(data).records:
                records[row.variant_id] = DummyStockRecord(row.model_dump())
        except ServiceCallError as error:
            logger.warning("inventory batch read failed for %d ids: %s", len(wanted), error)

        for variant_id in wanted:
            records.setdefault(
                variant_id, DummyStockRecord({"variant_id": variant_id, "available": 0})
            )
        return records
