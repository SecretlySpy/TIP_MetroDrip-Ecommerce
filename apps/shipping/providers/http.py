"""HTTP booking adapter — opt-in strangler for the fulfillment service.

Selected with `SHIPPING_PROVIDER=http` and `SHIPPING_SERVICE_URL`. Default
remains `jnt` / `simulated`. Failures return False so admin packing keeps the
manual-waybill fallback (never blocks order state transitions).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from apps.core.http import CallPolicy, ServiceCallError, call
from config.middleware import get_correlation_id

from ..models import ShipmentStatus
from . import ShippingProvider, register_provider

logger = logging.getLogger(__name__)

# Booking is not idempotent (each call mints a new waybill), so a retry could
# book the same shipment twice. attempts=1 until the service accepts an
# Idempotency-Key. The read timeout is generous because a real courier API sits
# behind it; packing is admin work, off the checkout critical path.
_BOOK_POLICY = CallPolicy(
    connect_timeout=2.0,
    read_timeout=10.0,
    attempts=1,
    breaker_key="fulfillment.book",
)


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
        try:
            data = call(
                "POST",
                f"{base}/v1/shipments/book",
                policy=_BOOK_POLICY,
                json=payload,
                service_token=getattr(settings, "SHIPPING_SERVICE_TOKEN", "") or "",
                token_setting_name="SHIPPING_SERVICE_TOKEN",
            )
        except ServiceCallError as error:
            # Enhancement-tier: a booking failure must never block the order
            # state transition, so this still degrades to the manual waybill.
            logger.warning("fulfillment book failed order=%s: %s", order.order_no, error)
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
