"""PayMongo integration adapter (D-2)."""

import base64
import os
import requests

from django.conf import settings
from .models import Payment, PaymentMethod, PaymentStatus

PAYMONGO_SECRET_KEY = getattr(settings, "PAYMONGO_SECRET_KEY", os.environ.get("PAYMONGO_SECRET_KEY", "sk_test_mock"))
PAYMONGO_API_URL = "https://api.paymongo.com/v1"

class PayMongoError(Exception):
    pass

def _get_auth_headers():
    auth_str = f"{PAYMONGO_SECRET_KEY}:"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

def create_checkout_session(order, success_url, cancel_url):
    """Create a PayMongo Checkout Session for the given Order.
    
    Returns the (checkout_url, session_id). If running in a fully mocked
    sandbox without real keys, returns a mock URL.
    """
    if PAYMONGO_SECRET_KEY == "sk_test_mock" or "mock" in PAYMONGO_SECRET_KEY:
        # Create a pending payment
        Payment.objects.create(
            order=order,
            provider_ref=f"mock_session_{order.order_no}",
            method=PaymentMethod.CARD,
            status=PaymentStatus.PENDING,
            amount=order.total
        )
        return f"{success_url}?mock_paid=true", f"mock_session_{order.order_no}"

    # Real API call
    line_items = []
    for item in order.items.select_related("variant__product"):
        line_items.append({
            "name": f"{item.variant.product.name} ({item.variant.sku})",
            "quantity": item.qty,
            "amount": item.price,
            "currency": "PHP",
        })
    
    if order.shipping_fee > 0:
        line_items.append({
            "name": "Shipping Fee",
            "quantity": 1,
            "amount": order.shipping_fee,
            "currency": "PHP",
        })

    payload = {
        "data": {
            "attributes": {
                "billing": {
                    "name": order.shipping_address.get("name"),
                    "email": order.shipping_address.get("email"),
                    "phone": order.shipping_address.get("phone"),
                },
                "send_email_receipt": False,
                "show_description": True,
                "show_line_items": True,
                "line_items": line_items,
                "payment_method_types": ["card", "gcash", "paymaya"],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "reference_number": order.order_no,
                "description": f"MetroDrip Order {order.order_no}",
            }
        }
    }

    response = requests.post(
        f"{PAYMONGO_API_URL}/checkout_sessions",
        json=payload,
        headers=_get_auth_headers(),
        timeout=10
    )

    if response.status_code != 200:
        raise PayMongoError(f"PayMongo API error: {response.text}")

    data = response.json().get("data", {})
    attributes = data.get("attributes", {})
    session_id = data.get("id")
    checkout_url = attributes.get("checkout_url")

    # Create Payment record
    Payment.objects.create(
        order=order,
        provider_ref=session_id,
        method=PaymentMethod.CARD, # Default placeholder until webhook confirms method
        status=PaymentStatus.PENDING,
        amount=order.total
    )

    return checkout_url, session_id
