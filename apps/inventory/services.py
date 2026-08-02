"""Inventory client for the FastAPI Microservice.

All stock operations are now delegated to the standalone FastAPI service.
Django acts as a client, either via synchronous HTTP (for reads/holds)
or async Redis Pub/Sub events (for commits/releases).
"""

import json
import logging
import os

import redis
import requests

logger = logging.getLogger(__name__)

# Fallback values for local dev without compose environment vars
INVENTORY_SERVICE_URL = os.environ.get("INVENTORY_SERVICE_URL", "http://127.0.0.1:8000")
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")


class InsufficientStock(Exception):
    pass


class InvalidReservationState(Exception):
    pass


class InvalidStockAdjustment(Exception):
    pass


class DummyReservation:
    def __init__(self, pk):
        self.pk = pk


def reserve_stock(*, variant_id, qty, session_key="", order=None):
    """
    Called by legacy code one by one. In a real microservice we would batch this.
    For simplicity, we call the batch API with one item.
    """
    if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
        raise ValueError("qty must be an integer of at least 1.")

    try:
        params = {"session_key": session_key}

        response = requests.post(
            f"{INVENTORY_SERVICE_URL}/reservations",
            json=[{"variant_id": variant_id, "qty": qty}],
            params=params,
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        res_id = data["reservations"][0]
        
        # We update the order_id in Django because FastAPI cannot insert it
        # while Django holds the uncommitted transaction for the new Order.
        if order:
            from apps.inventory.models import Reservation
            Reservation.objects.filter(pk=res_id).update(order=order)
            
        # Returns dummy reservation so caller can track reservation IDs
        return DummyReservation(res_id)
    except requests.HTTPError:
        if response.status_code == 400 and "Insufficient stock" in response.text:
            raise InsufficientStock(f"variant {variant_id} is short on stock") from None
        raise ValueError(f"Inventory service error: {response.text}") from None
    except Exception as e:
        raise ValueError(f"Failed to communicate with inventory service: {e}") from e


def release_reservation(reservation_id):
    """
    Fallback release. Instead of hitting the DB directly, publish to Redis.
    """
    try:
        r = redis.from_url(REDIS_URL)
        r.publish(
            "inventory_events",
            json.dumps({"type": "CheckoutCancelled", "data": {"reservations": [reservation_id]}}),
        )
    except Exception as e:
        logger.error(f"Failed to publish CheckoutCancelled for reservation {reservation_id}: {e}")
        return None
    return DummyReservation(reservation_id)


def commit_reservation(*, reservation_id, order):
    """
    Legacy sync commit; now we should just fire an event.
    """
    try:
        r = redis.from_url(REDIS_URL)
        r.publish(
            "inventory_events",
            json.dumps(
                {
                    "type": "OrderConfirmed",
                    "data": {"order_id": order.id, "reservations": [reservation_id]},
                }
            ),
        )
    except Exception as e:
        logger.error(f"Failed to publish OrderConfirmed for reservation {reservation_id}: {e}")
        return None
    return DummyReservation(reservation_id)


def adjust_stock(*, variant_id, delta, reason, ref_order=None):
    """Not implemented over HTTP yet in this demo."""
    raise NotImplementedError("adjust_stock is not implemented in the microservice stub.")


def release_expired_reservations(now=None):
    """Not implemented here. The microservice would have its own cron."""
    return 0


class DummyStockRecord:
    def __init__(self, data):
        self.variant_id = data.get("variant_id")
        self.qty_on_hand = data.get("qty_on_hand", 0)
        self.qty_reserved = data.get("qty_reserved", 0)
        self.low_stock_threshold = data.get("low_stock_threshold", 5)
        self.available = data.get("available", 0)


def scan_low_stock():
    """Not implemented over HTTP yet in this demo."""
    # Since this returns a queryset in the monolith, returning an empty list for now.
    return []


def get_stock_record(variant_id):
    try:
        response = requests.get(f"{INVENTORY_SERVICE_URL}/stock/{variant_id}", timeout=2)
        response.raise_for_status()
        return DummyStockRecord(response.json())
    except requests.HTTPError:
        raise ValueError(f"variant {variant_id} missing in inventory service") from None
    except Exception:
        # Fallback to zero availability if service is down
        return DummyStockRecord({"variant_id": variant_id, "available": 0})
