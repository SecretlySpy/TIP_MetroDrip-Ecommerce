"""Django admin configuration for the payments domain (C-1).

Payment records are webhook-driven (Hard Invariant 3) and read-only in admin.
"""

from django.contrib import admin

from apps.orders.money import format_centavos

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "method", "status", "amount_display", "provider_ref", "paid_at")
    list_filter = ("method", "status")
    search_fields = ("order__order_no", "provider_ref")
    readonly_fields = ("order", "method", "status", "amount_display", "provider_ref", "paid_at")

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return format_centavos(obj.amount)

    def has_add_permission(self, request):
        # Payments are created by the checkout/webhook flow only.
        return False

    def has_delete_permission(self, request, obj=None):
        return False
