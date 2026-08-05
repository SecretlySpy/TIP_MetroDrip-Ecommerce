"""Payment records — **merchant console** (FR Merchant-05).

Payment records are webhook-driven (Hard Invariant 3) and read-only in admin.
They sit beside orders because a merchant processing a refund needs the
transaction in front of them; the administrator console governs which payment
*methods* exist, not individual transactions.
"""

from django.contrib import admin

from apps.core.money import format_centavos
from config.consoles import merchant_site

from .models import Payment


@admin.register(Payment, site=merchant_site)
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
