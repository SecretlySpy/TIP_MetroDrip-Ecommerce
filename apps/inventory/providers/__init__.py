"""Inventory provider registry (mirrors payments/shipping/notifications).

`INVENTORY_PROVIDER = "local" | "service"`, default **local**: the in-process,
row-locked implementation is the only one that upholds Hard Invariants 1 & 4
transactionally today. The "service" provider delegates to the experimental
FastAPI microservice (D-07) and is an explicit opt-in until it implements the
full contract (commit/adjust/sweep/scan are stubs there).
"""

import abc

from django.conf import settings


class InventoryProvider(abc.ABC):
    @abc.abstractmethod
    def reserve_stock(self, *, variant_id, qty, session_key="", order=None, checkout_id=""): ...

    @abc.abstractmethod
    def reserve_lines(self, *, checkout_id, lines, session_key="", ttl_minutes=None):
        """Reserve every line atomically under one `checkout_id`, or nothing.

        `checkout_id` is minted by the caller *before* any write, so it exists
        while the Order still does not. That is what lets a caller compensate
        by telling the ledger to undo an id it supplied, instead of reaching
        into the ledger's tables to find rows the ledger created.
        """

    @abc.abstractmethod
    def commit_holds(self, *, checkout_id, order_no="", order_id=None, inside_transaction=False):
        """Convert a checkout group's ACTIVE holds into sales. Returns a count.

        `inside_transaction` warns the provider that the caller is holding a
        database transaction open, so any remote work must run on a tight,
        non-retrying budget (ADR-P3-028). In-process providers ignore it.
        """

    @abc.abstractmethod
    def release_holds(self, *, checkout_id):
        """Release a checkout group's ACTIVE holds. Unknown ids are a no-op."""

    @abc.abstractmethod
    def release_reservation(self, reservation_id): ...

    @abc.abstractmethod
    def commit_reservation(self, *, reservation_id, order): ...

    @abc.abstractmethod
    def adjust_stock(self, *, variant_id, delta, reason, ref_order=None): ...

    @abc.abstractmethod
    def release_expired_reservations(self, now=None): ...

    @abc.abstractmethod
    def scan_low_stock(self): ...

    @abc.abstractmethod
    def get_stock_record(self, variant_id): ...

    @abc.abstractmethod
    def get_stock_records(self, variant_ids):
        """Counters for many SKUs at once, as `{variant_id: record}`.

        Batch rather than a loop over `get_stock_record` because under the
        `service` provider each call is a separate HTTP round trip. The product
        detail page reads every variant of a product — 36 on the seeded catalog
        — which made a listing page ~36 sequential requests. Unknown ids read
        as zero availability, exactly as the single-record accessor does, so
        callers never have to distinguish "unstocked" from "missing".
        """


def get_inventory_provider() -> InventoryProvider:
    key = getattr(settings, "INVENTORY_PROVIDER", "local")
    if key == "service":
        from .service import ServiceInventoryProvider

        return ServiceInventoryProvider()
    from .local import LocalInventoryProvider

    return LocalInventoryProvider()
