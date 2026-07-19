"""Django admin configuration for the accounts domain (C-1).

Customer uses a UserAdmin-style layout since it is the AUTH_USER_MODEL.
WishlistItem is registered as a read-only convenience view.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Customer, WishlistItem


from apps.core.admin import ExportCsvMixin

@admin.register(Customer)
class CustomerAdmin(BaseUserAdmin, ExportCsvMixin):
    """Admin for the custom Customer user model (email-based, no username)."""

    # Override BaseUserAdmin fields that reference 'username' which doesn't exist.
    ordering = ("-date_joined",)
    list_display = ("email", "name", "phone", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email", "name", "phone")
    actions = ["export_as_csv"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("name", "phone", "addresses")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "name", "password1", "password2"),
        }),
    )
    readonly_fields = ("date_joined", "last_login")


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("customer", "product", "created_at")
    search_fields = ("customer__email", "product__name")
    readonly_fields = ("customer", "product", "created_at")

    def has_add_permission(self, request):
        # Wishlist items are managed by the storefront, not the admin.
        return False

    def has_delete_permission(self, request, obj=None):
        return False
