"""Django admin configuration for the inventory domain (C-1).

StockRecord is shown as an inline on the catalog's ProductVariant admin.
StockMovement is registered as a read-only view — append-only data cannot be
edited or deleted through the admin. Reservation is read-only for operational
visibility into active checkout holds.
"""

from django.contrib import admin

from .models import Reservation, StockMovement, StockRecord


class StockRecordInline(admin.StackedInline):
    """Show stock counters alongside a variant in the catalog admin."""

    model = StockRecord
    extra = 0
    fields = ("qty_on_hand", "qty_reserved", "available_display", "low_stock_threshold")
    readonly_fields = ("available_display",)

    @admin.display(description="Available (on hand − reserved)")
    def available_display(self, obj):
        if obj.pk is None:
            return "—"
        return obj.available


@admin.register(StockRecord)
class StockRecordAdmin(admin.ModelAdmin):
    list_display = (
        "variant",
        "qty_on_hand",
        "qty_reserved",
        "available_display",
        "low_stock_threshold",
    )
    list_filter = ("low_stock_threshold",)
    search_fields = ("variant__sku",)
    readonly_fields = ("available_display",)

    @admin.display(description="Available")
    def available_display(self, obj):
        return obj.available


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    """Append-only audit log — no edit or delete permitted."""

    list_display = ("variant", "delta", "reason", "ref_order", "created_at")
    list_filter = ("reason", "created_at")
    search_fields = ("variant__sku",)
    readonly_fields = ("variant", "delta", "reason", "ref_order", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        # Movements are created only through services.py — never through admin.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    """Operational view of checkout holds — read-only."""

    list_display = (
        "id",
        "variant",
        "qty",
        "status",
        "session_key_short",
        "expires_at",
        "created_at",
        "ended_at",
    )
    list_filter = ("status",)
    search_fields = ("variant__sku", "session_key")
    readonly_fields = (
        "variant",
        "qty",
        "status",
        "session_key",
        "order",
        "expires_at",
        "created_at",
        "ended_at",
    )

    @admin.display(description="Session")
    def session_key_short(self, obj):
        """Truncate session keys for the list view."""
        if obj.session_key:
            return obj.session_key[:12] + "…" if len(obj.session_key) > 12 else obj.session_key
        return "—"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
