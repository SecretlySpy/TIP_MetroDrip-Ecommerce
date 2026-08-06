"""FastAPI microservice inventory provider (D-07 experiment — OPT-IN ONLY).

Preserves the HTTP/Redis client from the microservice extraction. This provider
does NOT yet satisfy the full inventory contract: commits and releases are
fire-and-forget events, and adjust/sweep/scan are stubs. Until the service
implements them transactionally, `INVENTORY_PROVIDER = "service"` must never
run in an environment where the hard invariants are load-bearing.
"""

import logging
import os
import uuid

from django.conf import settings

from apps.core.http import CallPolicy, ServiceCallError, ServiceRejected, call
from apps.inventory.exceptions import (
    InsufficientStock,
    InvalidStockAdjustment,
    ReservationUnavailable,
)
from contracts.inventory_v1 import (
    ROUTE_COMMIT,
    ROUTE_RELEASE,
    ROUTE_RESERVATIONS,
    ROUTE_STOCK_BATCH,
    CommitRequest,
    CommitResponse,
    ReleaseResponse,
    ReserveRequest,
    ReserveResponse,
    StockBatchRequest,
    StockBatchResponse,
)

from . import InventoryProvider

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

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

    def commit_holds(self, *, checkout_id, order_no="", order_id=None):
        """Turn the group's holds into sales. Idempotent on the service side."""
        try:
            data = call(
                "POST",
                f"{_base_url()}{ROUTE_COMMIT.format(checkout_id=checkout_id)}",
                policy=_WRITE_POLICY,
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

    def adjust_stock(self, *, variant_id, delta, reason, ref_order=None):
        raise InvalidStockAdjustment(
            "adjust_stock is not implemented by the inventory microservice yet; "
            "use INVENTORY_PROVIDER='local' for stock adjustments."
        )

    def release_expired_reservations(self, now=None):
        # The microservice owns its own sweep; nothing to do from Django.
        return 0

    def scan_low_stock(self):
        logger.warning("scan_low_stock is not implemented by the inventory microservice yet.")
        return []

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
