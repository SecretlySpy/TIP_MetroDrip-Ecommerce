"""Inbound courier webhook (§7: `/api/webhooks/courier/`).

Carriers push delivery-status transitions here. Like the PayMongo handler
(ADR-D-003) this is signature-verified and fails closed when no secret is
configured — an unauthenticated endpoint that can mark orders Delivered would
let anyone close out someone else's order.

Idempotent: re-delivering the same status is a no-op, so carrier retries are
safe.
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.orders.models import IllegalTransition, OrderStatus

from .models import Shipment, ShipmentStatus

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Courier-Signature"

# Carrier vocabulary → our ShipmentStatus. Carriers differ in casing and
# wording, so match on a normalized token.
COURIER_STATUS_MAP = {
    "booked": ShipmentStatus.BOOKED,
    "picked_up": ShipmentStatus.IN_TRANSIT,
    "in_transit": ShipmentStatus.IN_TRANSIT,
    "intransit": ShipmentStatus.IN_TRANSIT,
    "out_for_delivery": ShipmentStatus.OUT_FOR_DELIVERY,
    "outfordelivery": ShipmentStatus.OUT_FOR_DELIVERY,
    "delivered": ShipmentStatus.DELIVERED,
    "failed": ShipmentStatus.FAILED,
    "failed_delivery": ShipmentStatus.FAILED,
    "returned": ShipmentStatus.FAILED,
}

# Shipment states that should also advance the order's own state machine.
# Only Delivered has an order-level counterpart; the rest are shipment detail.
ORDER_TRANSITION_FOR = {ShipmentStatus.DELIVERED: OrderStatus.DELIVERED}


def _signature_valid(request):
    """Verify the HMAC-SHA256 of the raw body under the courier secret."""
    secret = getattr(settings, "COURIER_WEBHOOK_SECRET", "")
    if not secret:
        logger.error("COURIER_WEBHOOK_SECRET unset; rejecting webhook (fail closed).")
        return False
    provided = request.headers.get(SIGNATURE_HEADER, "")
    expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    return bool(provided) and hmac.compare_digest(expected, provided)


@csrf_exempt
@require_POST
def courier_webhook(request):
    """Apply one carrier status update to its shipment (and maybe its order)."""
    if not _signature_valid(request):
        return HttpResponse(status=400)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    waybill = str(payload.get("waybill_no", "")).strip()
    raw_status = str(payload.get("status", "")).strip().lower().replace("-", "_").replace(" ", "_")
    if not waybill or not raw_status:
        return HttpResponse(status=400)

    new_status = COURIER_STATUS_MAP.get(raw_status)
    if new_status is None:
        # Unknown vocabulary is acknowledged so the carrier stops retrying,
        # but logged loudly so the mapping can be extended.
        logger.warning("Courier webhook: unmapped status %r for waybill %s", raw_status, waybill)
        return HttpResponse(status=200)

    try:
        shipment = Shipment.objects.select_related("order").get(waybill_no=waybill)
    except Shipment.DoesNotExist:
        # Acknowledge to stop retry storms; surface for reconciliation.
        logger.error("Courier webhook: unknown waybill %s", waybill)
        return HttpResponse(status=200)

    if shipment.status != new_status:
        shipment.status = new_status
        # Shipment.save() fires the Out-for-Delivery push on that edge (FR-27).
        shipment.save(update_fields=["status"])

    target = ORDER_TRANSITION_FOR.get(new_status)
    if target is not None and shipment.order.status != target:
        try:
            shipment.order.transition_to(target)
        except IllegalTransition:
            # e.g. the order was refunded before the carrier reported delivery.
            logger.warning(
                "Courier webhook: %s → %s rejected for %s",
                shipment.order.status,
                target,
                shipment.order.order_no,
            )

    return HttpResponse(status=200)
