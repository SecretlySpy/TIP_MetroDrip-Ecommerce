"""Simulated shipping provider (D-08)."""

import random

from django.utils import timezone

from ..models import ShipmentStatus
from . import ShippingProvider, register_provider


@register_provider("simulated")
class SimulatedShippingProvider(ShippingProvider):
    """Generates mock waybills for simulated shipping."""

    def book_shipment(self, shipment):
        if shipment.status != ShipmentStatus.PENDING:
            return False

        prefix = "SIM"
        number = "".join(str(random.randint(0, 9)) for _ in range(12))

        shipment.waybill_no = f"{prefix}{number}"
        shipment.tracking_url = f"https://tracker.example.com/track/{shipment.waybill_no}"
        shipment.status = ShipmentStatus.BOOKED
        shipment.booked_at = timezone.now()
        shipment.save(update_fields=["waybill_no", "tracking_url", "status", "booked_at"])
        return True
