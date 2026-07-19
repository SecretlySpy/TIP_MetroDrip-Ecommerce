"""Django admin configuration for the shipping domain (C-1).

Shipment includes a manual waybill entry field (FR-7 fallback) so the store
owner can enter tracking numbers even without J&T API integration.
"""

from django.contrib import admin

from .models import Shipment, ShippingZone


@admin.register(ShippingZone)
class ShippingZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "fee", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("order", "courier", "waybill_no", "status", "booked_at")
    list_filter = ("courier", "status")
    search_fields = ("order__order_no", "waybill_no")
    # waybill_no and tracking_url are editable — this is the manual fallback (FR-7).
    readonly_fields = ("order",)
    fieldsets = (
        (
            None,
            {
                "fields": ("order", "courier", "status", "booked_at"),
            },
        ),
        (
            "Tracking (FR-7: manual waybill entry fallback)",
            {
                "fields": ("waybill_no", "tracking_url"),
                "description": "Enter the waybill number and tracking URL manually if "
                "the courier API is unavailable.",
            },
        ),
    )
