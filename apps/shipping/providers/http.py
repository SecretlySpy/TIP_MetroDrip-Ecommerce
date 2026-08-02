"""HTTP booking adapter — opt-in strangler for the fulfillment service.

Selected with `SHIPPING_PROVIDER=http` and `SHIPPING_SERVICE_URL`. Default
remains `jnt` / `simulated`. Failures return False so admin packing keeps the
manual-waybill fallback (never blocks order state transitions).
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.utils import timezone

from config.middleware import get_correlation_id

from ..models import ShipmentStatus
from . import ShippingProvider, register_provider

logger = logging.getLogger(__name__)


@register_provider("http")
class HttpShippingProvider(ShippingProvider):
    """POST a booking DTO; apply waybill fields to the Django Shipment row."""

    def book_shipment(self, shipment) -> bool:
        if shipment.status != ShipmentStatus.PENDING:
            return False

        base = (getattr(settings, "SHIPPING_SERVICE_URL", "") or "").rstrip("/")
        if not base.startswith("http"):
            logger.error("SHIPPING_SERVICE_URL is not configured")
            return False

        order = shipment.order
        address = order.shipping_address or {}
        payload = {
            "order_no": order.order_no,
            "courier": shipment.courier or "jnt",
            "recipient_name": address.get("name", ""),
            "address_line1": address.get("address_line1", ""),
            "city": address.get("city", ""),
            "phone": address.get("phone", ""),
            "correlation_id": get_correlation_id() or None,
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        token = getattr(settings, "SHIPPING_SERVICE_TOKEN", "") or ""
        if token:
            headers["Authorization"] = f"Bearer {token}"
        cid = get_correlation_id()
        if cid:
            headers["X-Correlation-ID"] = cid

        try:
            response = requests.post(
                f"{base}/v1/shipments/book",
                json=payload,
                headers=headers,
                timeout=10,
            )
            if response.status_code >= 400:
                logger.warning("fulfillment book → %s", response.status_code)
                return False
            data = response.json()
        except Exception:
            logger.exception("fulfillment service unreachable order=%s", order.order_no)
            return False

        waybill = str(data.get("waybill_no") or "").strip()
        if not waybill:
            logger.warning("fulfillment book returned empty waybill")
            return False

        shipment.waybill_no = waybill
        shipment.tracking_url = str(data.get("tracking_url") or "")
        shipment.status = ShipmentStatus.BOOKED
        shipment.booked_at = timezone.now()
        shipment.save(update_fields=["waybill_no", "tracking_url", "status", "booked_at"])
        return True
