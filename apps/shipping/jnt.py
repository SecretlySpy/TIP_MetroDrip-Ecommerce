"""Mock J&T Express courier adapter (E-2)."""

import random

from django.utils import timezone

from .models import ShipmentStatus


def book_shipment(shipment):
    """Simulate booking a shipment with J&T API."""
    if shipment.status != ShipmentStatus.PENDING:
        return False

    # Generate mock waybill
    prefix = "JNT"
    number = "".join(str(random.randint(0, 9)) for _ in range(12))

    shipment.waybill_no = f"{prefix}{number}"
    shipment.tracking_url = (
        f"https://www.jtexpress.ph/trajectoryQuery?waybillNo={shipment.waybill_no}"
    )
    shipment.status = ShipmentStatus.BOOKED
    shipment.booked_at = timezone.now()
    shipment.save(update_fields=["waybill_no", "tracking_url", "status", "booked_at"])
    return True
