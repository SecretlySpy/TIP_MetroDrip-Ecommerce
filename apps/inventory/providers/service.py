"""FastAPI microservice inventory provider (D-07 experiment — OPT-IN ONLY).

Preserves the HTTP/Redis client from the microservice extraction. This provider
does NOT yet satisfy the full inventory contract: commits and releases are
fire-and-forget events, and adjust/sweep/scan are stubs. Until the service
implements them transactionally, `INVENTORY_PROVIDER = "service"` must never
run in an environment where the hard invariants are load-bearing.
"""

import json
import logging
import os

import redis
import requests

from apps.inventory.exceptions import InsufficientStock, InvalidStockAdjustment

from . import InventoryProvider

logger = logging.getLogger(__name__)

INVENTORY_SERVICE_URL = os.environ.get("INVENTORY_SERVICE_URL", "http://127.0.0.1:8000")
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")


class DummyReservation:
    """Minimal handle so callers can track service-side reservation IDs."""

    def __init__(self, pk):
        self.pk = pk


class DummyStockRecord:
    def __init__(self, data):
        self.variant_id = data.get("variant_id")
        self.qty_on_hand = data.get("qty_on_hand", 0)
        self.qty_reserved = data.get("qty_reserved", 0)
        self.low_stock_threshold = data.get("low_stock_threshold", 5)
        self.available = data.get("available", 0)


class ServiceInventoryProvider(InventoryProvider):
    def reserve_stock(self, *, variant_id, qty, session_key="", order=None):
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an integer of at least 1.")

        try:
            response = requests.post(
                f"{INVENTORY_SERVICE_URL}/reservations",
                json=[{"variant_id": variant_id, "qty": qty}],
                params={"session_key": session_key},
                timeout=5,
            )
            response.raise_for_status()
            reservation_id = response.json()["reservations"][0]

            # The service cannot see Django's uncommitted Order row, so the
            # order link is written on this side.
            if order:
                from apps.inventory.models import Reservation

                Reservation.objects.filter(pk=reservation_id).update(order=order)
            return DummyReservation(reservation_id)
        except requests.HTTPError:
            if response.status_code == 400 and "Insufficient stock" in response.text:
                raise InsufficientStock(f"variant {variant_id} is short on stock") from None
            raise ValueError(f"Inventory service error: {response.text}") from None
        except Exception as error:
            raise ValueError(f"Failed to communicate with inventory service: {error}") from error

    def release_reservation(self, reservation_id):
        try:
            redis.from_url(REDIS_URL).publish(
                "inventory_events",
                json.dumps(
                    {"type": "CheckoutCancelled", "data": {"reservations": [reservation_id]}}
                ),
            )
        except Exception as error:
            logger.error("Failed to publish CheckoutCancelled for %s: %s", reservation_id, error)
            return None
        return DummyReservation(reservation_id)

    def commit_reservation(self, *, reservation_id, order):
        try:
            redis.from_url(REDIS_URL).publish(
                "inventory_events",
                json.dumps(
                    {
                        "type": "OrderConfirmed",
                        "data": {"order_id": order.id, "reservations": [reservation_id]},
                    }
                ),
            )
        except Exception as error:
            logger.error("Failed to publish OrderConfirmed for %s: %s", reservation_id, error)
            return None
        return DummyReservation(reservation_id)

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
        try:
            response = requests.get(f"{INVENTORY_SERVICE_URL}/stock/{variant_id}", timeout=2)
            response.raise_for_status()
            return DummyStockRecord(response.json())
        except requests.HTTPError:
            raise ValueError(f"variant {variant_id} missing in inventory service") from None
        except Exception:
            # Service down → read as sold out rather than oversell.
            return DummyStockRecord({"variant_id": variant_id, "available": 0})
