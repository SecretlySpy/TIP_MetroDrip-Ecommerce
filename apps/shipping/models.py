"""Shipment record per order (§4). J&T in v1 (D-01), behind a provider
interface added in Epic E; manual waybill entry is the launch fallback (FR-7)."""

from django.db import models


class ShippingZone(models.Model):
    """Zone-based flat shipping rates (D-02). NCR, Luzon, VisMin, etc."""

    name = models.CharField(max_length=50, unique=True)
    fee = models.PositiveIntegerField(help_text="Flat fee in centavos")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ShipmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    BOOKED = "booked", "Booked"
    IN_TRANSIT = "in_transit", "In Transit"
    # Distinct status because FR-12 sends an SMS specifically at this point.
    OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"


class Shipment(models.Model):
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="shipment")
    courier = models.CharField(max_length=20, default="jnt")
    waybill_no = models.CharField(max_length=64, blank=True)  # blank until booked/manually entered
    tracking_url = models.URLField(blank=True)
    status = models.CharField(
        max_length=20, choices=ShipmentStatus.choices, default=ShipmentStatus.PENDING
    )
    booked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.order_id} {self.courier} {self.waybill_no or '(no waybill)'}"
