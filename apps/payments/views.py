"""PayMongo webhook endpoint (D-3).

Hard Invariant 3: this signature-verified, idempotent handler is the ONLY
production path that confirms payment. A missing or invalid signature is
rejected before any payload parsing.
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.core.signing import Signer
from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.notifications.services import send_order_confirmation
from apps.notifications.sms import send_sms
from apps.orders.models import Order

from .services import confirm_order_paid

logger = logging.getLogger(__name__)

# PayMongo reports Maya as "paymaya"; our Payment.method enum says "maya".
_METHOD_ALIASES = {"paymaya": "maya"}

_PAID_EVENT_TYPES = {"payment.paid", "checkout_session.payment.paid"}


def _signature_valid(request):
    """Verify the `Paymongo-Signature: t=<ts>,te=<sig>,li=<sig>` HMAC header.

    The signed message is `<timestamp>.<raw body>` with HMAC-SHA256 under the
    webhook secret; `te` covers test mode and `li` live mode. No configured
    secret means NO webhook may ever be processed — fail closed.
    """
    secret = settings.PAYMONGO_WEBHOOK_SECRET
    if not secret:
        logger.error("PAYMONGO_WEBHOOK_SECRET unset; rejecting webhook (fail closed).")
        return False

    header = request.headers.get("Paymongo-Signature", "")
    parts = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
    timestamp = parts.get("t")
    if not timestamp:
        return False

    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + request.body, hashlib.sha256
    ).hexdigest()
    return any(hmac.compare_digest(expected, parts.get(key, "")) for key in ("te", "li"))


def _extract_reference_and_method(payload):
    """Pull our order_no and the used payment method out of either event shape."""
    resource = payload.get("data", {}).get("attributes", {}).get("data", {})
    attributes = resource.get("attributes", {})

    reference = attributes.get("reference_number", "")
    if not reference:
        description = attributes.get("description", "")
        if description.startswith("MetroDrip Order "):
            reference = description.removeprefix("MetroDrip Order ")

    method = attributes.get("source", {}).get("type", "")
    if not method:
        # checkout_session events nest the actual payment resource(s).
        payments = attributes.get("payments", [])
        if payments:
            method = payments[0].get("attributes", {}).get("source", {}).get("type", "")
    return reference, _METHOD_ALIASES.get(method, method)


@csrf_exempt
@require_POST
def paymongo_webhook(request):
    if not _signature_valid(request):
        return HttpResponse(status=400)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event_type = payload.get("data", {}).get("attributes", {}).get("type")
    if event_type not in _PAID_EVENT_TYPES:
        # Unsubscribed event types are acknowledged so PayMongo stops retrying.
        return HttpResponse(status=200)

    reference, method = _extract_reference_and_method(payload)
    if not reference:
        logger.error("Paid webhook without an order reference; payload type=%s", event_type)
        return HttpResponse(status=400)

    try:
        order = Order.objects.get(order_no=reference)
    except Order.DoesNotExist:
        # Acknowledge to stop retry storms, but keep the mismatch loud in logs
        # for the daily PayMongo reconciliation (§13).
        logger.error("Paid webhook references unknown order %s", reference)
        return HttpResponse(status=200)

    newly_confirmed = confirm_order_paid(order=order, method=method or None)

    if newly_confirmed:
        # Notifications are enhancement-tier (§7): failures must never turn a
        # confirmed payment into a webhook error/retry loop.
        try:
            token = Signer().sign(str(order.pk))
            status_url = request.build_absolute_uri(
                reverse("storefront:order-status", args=[token])
            )
            send_order_confirmation(order, status_url)
            phone = order.shipping_address.get("phone")
            if phone:
                send_sms(
                    phone,
                    f"MetroDrip: order {order.order_no} is paid. Track it here: {status_url}",
                )
        except Exception:
            logger.exception("Post-payment notifications failed for %s", order.order_no)

    return HttpResponse(status=200)
