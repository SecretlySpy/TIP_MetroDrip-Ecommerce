"""Django admin configuration for the reviews domain (C-1).

Reviews have moderation actions (approve/reject) per FR-17. Nothing with
status != approved may ever render publicly (M4.5 gate).
"""

from django.contrib import admin

from .models import Review, ReviewStatus


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "customer", "rating", "status", "created_at")
    list_filter = ("status", "rating", "created_at")
    search_fields = ("product__name", "customer__email", "body")
    readonly_fields = ("customer", "product", "order", "rating", "body", "created_at")
    actions = ["approve_reviews", "reject_reviews"]

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        updated = queryset.filter(status=ReviewStatus.PENDING).update(status=ReviewStatus.APPROVED)
        self.message_user(request, f"Approved {updated} review(s).")

    @admin.action(description="Reject selected reviews")
    def reject_reviews(self, request, queryset):
        updated = queryset.filter(status=ReviewStatus.PENDING).update(status=ReviewStatus.REJECTED)
        self.message_user(request, f"Rejected {updated} review(s).")

    def has_add_permission(self, request):
        # Reviews are submitted through the storefront only.
        return False

    def has_delete_permission(self, request, obj=None):
        return False
