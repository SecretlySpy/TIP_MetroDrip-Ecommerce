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
    def reserve_stock(self, *, variant_id, qty, session_key="", order=None): ...

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


def get_inventory_provider() -> InventoryProvider:
    key = getattr(settings, "INVENTORY_PROVIDER", "local")
    if key == "service":
        from .service import ServiceInventoryProvider

        return ServiceInventoryProvider()
    from .local import LocalInventoryProvider

    return LocalInventoryProvider()
