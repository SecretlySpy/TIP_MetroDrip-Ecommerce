"""Inventory administration — **merchant console** (FR Merchant-02).

StockRecord is shown as an inline on the catalog's ProductVariant admin.
StockMovement is registered as a read-only view — append-only data cannot be
edited or deleted through the admin. Reservation is read-only for operational
visibility into active checkout holds.
"""

from django.contrib import admin
from django.db.models import F
from django.utils.html import format_html

from config.consoles import merchant_site

from .models import Reservation, StockMovement, StockRecord


class LowStockFilter(admin.SimpleListFilter):
    """FR-9's dashboard leg: find SKUs at or below their reorder threshold.

    The comparison is on *availability* (on hand − reserved), matching the
    scan job — shelf count alone would hide units already promised to holds.
    """

    title = "stock level"
    parameter_name = "stock_level"

    def lookups(self, request, model_admin):
        return (("low", "Low stock (needs restock)"), ("ok", "Healthy"))

    def queryset(self, request, queryset):
        # `available_units` is annotated by StockRecordAdmin.get_queryset().
        if self.value() == "low":
            return queryset.filter(available_units__lte=F("low_stock_threshold"))
        if self.value() == "ok":
            return queryset.filter(available_units__gt=F("low_stock_threshold"))
        return queryset


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


@admin.register(StockRecord, site=merchant_site)
class StockRecordAdmin(admin.ModelAdmin):
    list_display = (
        "variant",
        "qty_on_hand",
        "qty_reserved",
        "available_display",
        "low_stock_threshold",
        "stock_flag",
    )
    list_filter = (LowStockFilter, "low_stock_threshold")
    search_fields = ("variant__sku",)
    readonly_fields = ("available_display",)

    def get_queryset(self, request):
        # Annotate once so the filter can compare in SQL and the flag column
        # doesn't trigger a query per row.
        return (
            super()
            .get_queryset(request)
            .select_related("variant", "variant__product")
            .annotate(available_units=F("qty_on_hand") - F("qty_reserved"))
        )

    @admin.display(description="Available", ordering="available_units")
    def available_display(self, obj):
        return obj.available

    @admin.display(description="Status")
    def stock_flag(self, obj):
        """Visual low-stock badge (FR-9), with the word as a non-colour cue."""
        if obj.available <= 0:
            return format_html(
                '<span style="background:#C2282D;color:#fff;padding:2px 8px;'
                'border-radius:4px;font-weight:600;">OUT</span>'
            )
        if obj.available <= obj.low_stock_threshold:
            return format_html(
                '<span style="background:#C8F031;color:#141414;padding:2px 8px;'
                'border-radius:4px;font-weight:600;">LOW</span>'
            )
        return format_html('<span style="color:#63635C;">OK</span>')


@admin.register(StockMovement, site=merchant_site)
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


@admin.register(Reservation, site=merchant_site)
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
