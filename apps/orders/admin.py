"""Order administration — **merchant console** (FR Merchant-03/04/05/06).

Order status is displayed but never editable through the admin — all state
transitions must go through Order.transition_to() per Hard Invariant 5.
OrderItem is shown inline on the order detail page.

Fulfilment is the seller's work, so orders live only on the merchant console.
Administrators audit them through the audit trail rather than by holding a
second copy of this screen (ADR-F-001).
"""

import logging

from django.contrib import admin
from django.db import transaction

from apps.core.admin import ExportCsvMixin
from apps.core.money import format_centavos
from config.consoles import merchant_site

from .models import Order, OrderItem

logger = logging.getLogger(__name__)


class OrderItemInline(admin.TabularInline):
    """Line items within an order — read-only historical data."""

    model = OrderItem
    extra = 0
    fields = ("variant", "qty", "unit_price_display")
    readonly_fields = ("variant", "qty", "unit_price_display")

    @admin.display(description="Unit Price")
    def unit_price_display(self, obj):
        if obj.pk is None:
            return "—"
        return format_centavos(obj.unit_price_snapshot)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order, site=merchant_site)
class OrderAdmin(ExportCsvMixin, admin.ModelAdmin):
    list_display = (
        "order_no",
        "customer",
        "status",
        "subtotal_display",
        "shipping_fee_display",
        "total_display",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("order_no", "customer__email")
    readonly_fields = (
        "order_no",
        "customer",
        "status",
        "subtotal_display",
        "shipping_fee_display",
        "total_display",
        "shipping_address",
        "created_at",
    )
    inlines = [OrderItemInline]
    ordering = ("-created_at",)

    @admin.display(description="Subtotal")
    def subtotal_display(self, obj):
        return format_centavos(obj.subtotal)

    @admin.display(description="Shipping")
    def shipping_fee_display(self, obj):
        return format_centavos(obj.shipping_fee)

    @admin.display(description="Total")
    def total_display(self, obj):
        return format_centavos(obj.total)

    def has_add_permission(self, request):
        return False

    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()
        custom_urls = [
            path(
                "sales-report/",
                self.admin_site.admin_view(self.sales_report_view),
                name="orders_order_sales_report",
            ),
            path(
                "<path:object_id>/invoice/",
                self.admin_site.admin_view(self.invoice_view),
                name="orders_order_invoice",
            ),
            path(
                "<path:object_id>/packing-slip/",
                self.admin_site.admin_view(self.packing_slip_view),
                name="orders_order_packing_slip",
            ),
        ]
        return custom_urls + urls

    def sales_report_view(self, request):
        from django.db.models import Count, Sum
        from django.shortcuts import render

        from apps.orders.models import Order

        # Revenue counts every order whose payment was confirmed and not
        # reversed — i.e. paid and all later fulfillment states. (The previous
        # list used status names that don't exist in OrderStatus.)
        metrics = Order.objects.filter(
            status__in=["paid", "packed", "shipped", "delivered"]
        ).aggregate(total_revenue=Sum("total"), total_orders=Count("id"))

        total_revenue_display = format_centavos(metrics["total_revenue"] or 0)

        # Pending vs completed counts
        status_counts = Order.objects.values("status").annotate(count=Count("id"))

        context = {
            **self.admin_site.each_context(request),
            "title": "Sales & Analytics Report",
            "total_revenue": total_revenue_display,
            "total_orders": metrics["total_orders"] or 0,
            "status_counts": status_counts,
        }
        return render(request, "admin/orders/order/sales_report.html", context)

    def invoice_view(self, request, object_id):
        from django.shortcuts import get_object_or_404, render

        from .models import Order

        order = get_object_or_404(Order, pk=object_id)
        return render(request, "admin/orders/order/invoice.html", {"order": order})

    def packing_slip_view(self, request, object_id):
        """FR-19: warehouse pick list — same order, no prices."""
        from django.shortcuts import get_object_or_404, render

        from .models import Order

        order = get_object_or_404(
            Order.objects.select_related("shipment").prefetch_related("items__variant__product"),
            pk=object_id,
        )
        return render(
            request,
            "admin/orders/order/packing_slip.html",
            {"order": order, "total_units": sum(item.qty for item in order.items.all())},
        )

    def has_delete_permission(self, request, obj=None):
        return False

    actions = [
        "mark_as_packed",
        "mark_as_shipped",
        "mark_as_cancelled",
        "mark_as_refunded",
        "export_as_csv",
    ]

    @admin.action(description="Transition selected to PACKED (books J&T shipment)")
    def mark_as_packed(self, request, queryset):
        from django.contrib.admin.models import CHANGE, LogEntry
        from django.contrib.contenttypes.models import ContentType

        from apps.orders.models import IllegalTransition, OrderStatus
        from apps.shipping.providers import get_shipping_provider

        provider = get_shipping_provider()
        from apps.shipping.models import Shipment

        success, failed = 0, 0
        for order in queryset:
            try:
                order.transition_to(OrderStatus.PACKED)
                # E-2: Create/Book shipment
                shipment, _ = Shipment.objects.get_or_create(order=order)
                provider.book_shipment(shipment)

                # F-2: Audit log
                LogEntry.objects.log_action(
                    user_id=request.user.id,
                    content_type_id=ContentType.objects.get_for_model(order).pk,
                    object_id=order.pk,
                    object_repr=str(order),
                    action_flag=CHANGE,
                    change_message="Transitioned to PACKED and booked shipment.",
                )

                success += 1
            except IllegalTransition as e:
                self.message_user(request, str(e), level="ERROR")
                failed += 1
        self.message_user(request, f"{success} orders packed. {failed} failed.")

    @admin.action(description="Transition selected to SHIPPED (triggers notifications)")
    def mark_as_shipped(self, request, queryset):
        from django.contrib.admin.models import CHANGE, LogEntry
        from django.contrib.contenttypes.models import ContentType

        from apps.notifications.sms import send_sms
        from apps.orders.models import IllegalTransition, OrderStatus
        from apps.shipping.models import ShipmentStatus

        success, failed = 0, 0
        for order in queryset:
            try:
                order.transition_to(OrderStatus.SHIPPED)
                # Update shipment status
                if hasattr(order, "shipment"):
                    order.shipment.status = ShipmentStatus.IN_TRANSIT
                    order.shipment.save(update_fields=["status"])

                # E-3: Notifications
                phone = order.shipping_address.get("phone")
                if phone:
                    tracking = order.shipment.waybill_no if hasattr(order, "shipment") else ""
                    send_sms(
                        phone, f"MetroDrip: Order {order.order_no} is SHIPPED! Tracking: {tracking}"
                    )

                # F-2: Audit log
                LogEntry.objects.log_action(
                    user_id=request.user.id,
                    content_type_id=ContentType.objects.get_for_model(order).pk,
                    object_id=order.pk,
                    object_repr=str(order),
                    action_flag=CHANGE,
                    change_message="Transitioned to SHIPPED and sent SMS.",
                )

                success += 1
            except IllegalTransition as e:
                self.message_user(request, str(e), level="ERROR")
                failed += 1
        self.message_user(request, f"{success} orders shipped. {failed} failed.")

    @admin.action(description="Transition selected to CANCELLED (releases reservation)")
    def mark_as_cancelled(self, request, queryset):
        from apps.inventory.services import release_holds
        from apps.orders.models import IllegalTransition, OrderStatus, StockHoldState

        success, failed = 0, 0
        for order in queryset:
            try:
                with transaction.atomic():
                    order.transition_to(OrderStatus.CANCELLED)
                    # Cancelling a pending order returns its holds (ADR-A-011).
                    # Released by `checkout_id` rather than by reading the ledger's
                    # rows: an active hold belongs to a checkout attempt, and only
                    # becomes linked to an order when it is committed as a sale. The
                    # StockHold receipt is what ties the two together on this side.
                    for hold in order.stock_holds.filter(state=StockHoldState.ACTIVE):
                        release_holds(checkout_id=hold.checkout_id)
                    order.stock_holds.filter(state=StockHoldState.ACTIVE).update(
                        state=StockHoldState.RELEASED
                    )
                success += 1
            except IllegalTransition as e:
                self.message_user(request, str(e), level="ERROR")
                failed += 1
            except Exception as e:
                # Same reasoning as mark_as_refunded (ADR-P3-027). Release is the
                # safe direction — a hold left active expires on the TTL sweep —
                # so a rolled-back cancel costs at most RESERVATION_TTL_MINUTES of
                # under-selling and can never oversell.
                logger.exception("Cancel failed for order %s", order.order_no)
                self.message_user(
                    request, f"{order.order_no}: hold release failed ({e}).", level="ERROR"
                )
                failed += 1
        self.message_user(request, f"{success} orders cancelled. {failed} failed.")

    @admin.action(description="Transition selected to REFUNDED (restores stock)")
    def mark_as_refunded(self, request, queryset):
        """Refund each selected order and restore its lines, one order at a time.

        **The transaction is per order, not per queryset** (ADR-P3-027). A refund
        is a complete unit of work on its own: order B failing to restore is no
        reason to un-refund order A, and a queryset-wide block would make a
        merchant's whole selection hostage to its worst row.

        Within one order the transition and *every* line restoration now commit
        together. Previously the transition ran first and the lines followed in a
        bare loop, so a failure on line 2 of 3 left the order REFUNDED with only
        part of its stock back — and because only IllegalTransition was caught,
        that failure also escaped the action, skipping every remaining order with
        a 500 rather than reporting which one broke.

        **Known limit under INVENTORY_PROVIDER=service.** `adjust_stock` is then
        an HTTP call to a ledger writing on its own connection, so this block
        cannot roll its writes back — a mid-loop failure would roll back the
        order transition while the ledger keeps the lines it already applied, and
        a retry would apply them a second time because a signed delta is not
        idempotent. That direction is an oversell risk, which is why it is called
        out here rather than left to be discovered: the refund path is an unmet
        precondition for selecting `service`, tracked in ADR-P3-027. The default
        provider is `local` (ADR-P3-025), where this block is exact.
        """
        from apps.inventory.models import MovementReason
        from apps.inventory.services import adjust_stock
        from apps.orders.models import IllegalTransition, OrderStatus

        success, failed = 0, 0
        for order in queryset:
            try:
                with transaction.atomic():
                    order.transition_to(OrderStatus.REFUNDED)
                    # E-4: Ledger sync restore
                    for item in order.items.all():
                        adjust_stock(
                            variant_id=item.variant_id,
                            delta=item.qty,
                            reason=MovementReason.RETURN,
                            ref_order=order,
                        )
                success += 1
            except IllegalTransition as e:
                self.message_user(request, str(e), level="ERROR")
                failed += 1
            except Exception as e:
                # A ledger fault is not a client error and must not abort the
                # rest of the selection. The block above already rolled this
                # order back whole, so naming it and moving on is safe.
                logger.exception("Refund failed for order %s", order.order_no)
                self.message_user(
                    request, f"{order.order_no}: stock restore failed ({e}).", level="ERROR"
                )
                failed += 1
        self.message_user(request, f"{success} orders refunded. {failed} failed.")
