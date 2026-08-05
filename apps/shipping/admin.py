"""Shipping administration — the one domain that spans **both** consoles.

`ShippingZone` sets the fee every checkout charges, which is a platform-wide
commercial setting: administrator console (FR Admin-04). `Shipment` is the
waybill for one order, which is fulfilment work: merchant console
(FR Merchant-03/04). Splitting them is the point of ADR-F-001 — a merchant can
dispatch parcels all day without being able to change what customers are
charged to receive them.

Shipment includes a manual waybill entry field (FR-7 fallback) so the store
owner can enter tracking numbers even without J&T API integration.
"""

from django.contrib import admin

from config.consoles import merchant_site

from .models import Shipment, ShippingZone


@admin.register(ShippingZone)  # administrator console (the default site)
class ShippingZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "fee_display", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)

    @admin.display(description="Fee", ordering="fee")
    def fee_display(self, obj):
        """Show the stored centavos as pesos.

        The raw column is an integer count of centavos (Hard Invariant: money is
        never a float), so an unformatted list column reads "35000" for ₱350.00
        — an easy way for an administrator to set a fee 100× too high.
        """
        from apps.core.money import format_centavos

        return format_centavos(obj.fee)


@admin.register(Shipment, site=merchant_site)
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
