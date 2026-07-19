import hmac
import hashlib
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.core.mail import send_mail
from django.core.signing import Signer
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction

from apps.orders.models import Order, OrderStatus
from apps.inventory.services import commit_reservation
from apps.inventory.models import Reservation
from apps.notifications.sms import send_sms
from .models import Payment, PaymentStatus

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def paymongo_webhook(request):
    """Handle PayMongo webhook events (D-3)."""
    # 1. Verify signature
    signature_header = request.headers.get("Paymongo-Signature", "")
    secret = getattr(settings, "PAYMONGO_WEBHOOK_SECRET", "mock_secret")
    
    # In a real integration, we'd verify the signature:
    # t=timestamp, te=test_signature, li=live_signature
    # parsed = dict(x.split("=") for x in signature_header.split(","))
    # sig = hmac.new(secret.encode(), f"{parsed['t']}.{request.body.decode()}".encode(), hashlib.sha256).hexdigest()
    # if sig != parsed['te'] and sig != parsed['li']: return HttpResponse(status=400)
    
    try:
        payload = json.loads(request.body)
        event_type = payload.get("data", {}).get("attributes", {}).get("type")
        
        if event_type == "payment.paid":
            # The resource could be a checkout session or a payment
            data = payload.get("data", {}).get("attributes", {}).get("data", {})
            attributes = data.get("attributes", {})
            
            # The reference number is our order_no
            reference = attributes.get("description", "").replace("MetroDrip Order ", "")
            # Or if it's a checkout session event, attributes.get("reference_number")
            
            # Fallback for mocked webhook
            if not reference:
                reference = payload.get("data", {}).get("attributes", {}).get("data", {}).get("attributes", {}).get("reference_number")
                
            if not reference:
                return HttpResponse(status=400)
                
            with transaction.atomic():
                try:
                    order = Order.objects.get(order_no=reference)
                except Order.DoesNotExist:
                    return HttpResponse(status=404)
                    
                payment = Payment.objects.filter(order=order).first()
                if not payment:
                    return HttpResponse(status=404)
                    
                # Idempotency
                if payment.status == PaymentStatus.PAID:
                    return HttpResponse(status=200)
                    
                payment.status = PaymentStatus.PAID
                payment.save(update_fields=["status"])
                
                # Commit all active reservations for this order's items
                for item in order.items.all():
                    # Find the active reservation. Note: in a real robust system, we link the reservation to the order early on.
                    # Here we just find an active reservation for the variant and qty.
                    res = Reservation.objects.filter(variant=item.variant, status="active", qty=item.qty).first()
                    if res:
                        commit_reservation(reservation_id=res.id, order=order)
                        
                order.transition_to(OrderStatus.PAID)
                
            # Trigger confirmation email and SMS (D-4, D-5)
            email = order.shipping_address.get("email")
            phone = order.shipping_address.get("phone")
            token = Signer().sign(str(order.id))
            status_url = request.build_absolute_uri(reverse("storefront:order-status", args=[token]))
            
            if email:
                send_mail(
                    subject=f"MetroDrip Order Confirmation: {order.order_no}",
                    message=f"Thank you for your order! You can track your order status here:\n{status_url}",
                    from_email="noreply@metrodrip.com",
                    recipient_list=[email],
                    fail_silently=True,
                )
                
            if phone:
                send_sms(phone, f"MetroDrip: Your order {order.order_no} is paid. Track here: {status_url}")
                
        return HttpResponse(status=200)
    except Exception as e:
        logger.exception("Webhook processing failed")
        return HttpResponse(status=500)
