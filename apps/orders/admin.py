"""Django admin configuration for the orders domain (C-1).

Order status is displayed but never editable through the admin — all state
transitions must go through Order.transition_to() per Hard Invariant 5.
OrderItem is shown inline on the order detail page.
"""

from django.contrib import admin

from apps.orders.money import format_centavos

from .models import Order, OrderItem


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


from apps.core.admin import ExportCsvMixin

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin, ExportCsvMixin):
    list_display = (
        "order_no", "customer", "status", "subtotal_display",
        "shipping_fee_display", "total_display", "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("order_no", "customer__email")
    readonly_fields = (
        "order_no", "customer", "status", "subtotal_display",
        "shipping_fee_display", "total_display", "shipping_address", "created_at",
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
            path("sales-report/", self.admin_site.admin_view(self.sales_report_view), name="orders_order_sales_report"),
            path("<path:object_id>/invoice/", self.admin_site.admin_view(self.invoice_view), name="orders_order_invoice"),
        ]
        return custom_urls + urls

    def sales_report_view(self, request):
        from django.shortcuts import render
        from django.db.models import Sum, Count
        from apps.orders.models import Order
        
        # Aggregate data
        metrics = Order.objects.filter(status__in=["completed", "shipped", "packed", "processing"]).aggregate(
            total_revenue=Sum("total"),
            total_orders=Count("id")
        )
        
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

    def has_delete_permission(self, request, obj=None):
        return False

    actions = ["mark_as_packed", "mark_as_shipped", "mark_as_cancelled", "mark_as_refunded", "export_as_csv"]

    @admin.action(description="Transition selected to PACKED (books J&T shipment)")
    def mark_as_packed(self, request, queryset):
        from apps.orders.models import OrderStatus, IllegalTransition
        from apps.shipping.models import Shipment
        from apps.shipping.jnt import book_shipment
        from django.contrib.admin.models import LogEntry, CHANGE
        from django.contrib.contenttypes.models import ContentType
        
        success, failed = 0, 0
        for order in queryset:
            try:
                order.transition_to(OrderStatus.PACKED)
                # E-2: Create/Book shipment
                shipment, _ = Shipment.objects.get_or_create(order=order)
                book_shipment(shipment)
                
                # F-2: Audit log
                LogEntry.objects.log_action(
                    user_id=request.user.id,
                    content_type_id=ContentType.objects.get_for_model(order).pk,
                    object_id=order.pk,
                    object_repr=str(order),
                    action_flag=CHANGE,
                    change_message="Transitioned to PACKED and booked shipment."
                )
                
                success += 1
            except IllegalTransition as e:
                self.message_user(request, str(e), level="ERROR")
                failed += 1
        self.message_user(request, f"{success} orders packed. {failed} failed.")

    @admin.action(description="Transition selected to SHIPPED (triggers notifications)")
    def mark_as_shipped(self, request, queryset):
        from apps.orders.models import OrderStatus, IllegalTransition
        from apps.shipping.models import ShipmentStatus
        from apps.notifications.sms import send_sms
        from django.contrib.admin.models import LogEntry, CHANGE
        from django.contrib.contenttypes.models import ContentType
        
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
                    send_sms(phone, f"MetroDrip: Order {order.order_no} is SHIPPED! Tracking: {tracking}")
                    
                # F-2: Audit log
                LogEntry.objects.log_action(
                    user_id=request.user.id,
                    content_type_id=ContentType.objects.get_for_model(order).pk,
                    object_id=order.pk,
                    object_repr=str(order),
                    action_flag=CHANGE,
                    change_message="Transitioned to SHIPPED and sent SMS."
                )
                    
                success += 1
            except IllegalTransition as e:
                self.message_user(request, str(e), level="ERROR")
                failed += 1
        self.message_user(request, f"{success} orders shipped. {failed} failed.")

    @admin.action(description="Transition selected to CANCELLED (releases reservation)")
    def mark_as_cancelled(self, request, queryset):
        from apps.orders.models import OrderStatus, IllegalTransition
        from apps.inventory.services import release_reservation
        from apps.inventory.models import Reservation
        
        success, failed = 0, 0
        for order in queryset:
            try:
                order.transition_to(OrderStatus.CANCELLED)
                # Free active reservations for this order. We'd usually look it up via session or order
                for res in Reservation.objects.filter(order=order):
                    release_reservation(res.id)
                success += 1
            except IllegalTransition as e:
                self.message_user(request, str(e), level="ERROR")
                failed += 1
        self.message_user(request, f"{success} orders cancelled. {failed} failed.")

    @admin.action(description="Transition selected to REFUNDED (restores stock)")
    def mark_as_refunded(self, request, queryset):
        from apps.orders.models import OrderStatus, IllegalTransition
        from apps.inventory.services import adjust_stock
        from apps.inventory.models import MovementReason
        
        success, failed = 0, 0
        for order in queryset:
            try:
                order.transition_to(OrderStatus.REFUNDED)
                # E-4: Ledger sync restore
                for item in order.items.all():
                    adjust_stock(
                        variant_id=item.variant_id,
                        delta=item.qty,
                        reason=MovementReason.RETURN,
                        ref_order=order
                    )
                success += 1
            except IllegalTransition as e:
                self.message_user(request, str(e), level="ERROR")
                failed += 1
        self.message_user(request, f"{success} orders refunded. {failed} failed.")
