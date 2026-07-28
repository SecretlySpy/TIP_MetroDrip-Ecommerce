"""Account and role administration — **administrator console** (FR Admin-02/03/05).

Everything here is registered on the default site, which `MetroDripAdminConfig`
points at `AdministratorSite`. Customer records, console roles, and the audit
trail are governance, not selling, so the merchant console never sees them
(ADR-F-001).

Two privilege tiers exist inside this console:

* any administrator may read accounts and activate or suspend a shopper;
* only a **superuser** may change `role`, staff/superuser status, groups, or
  permissions — that is the "authorized administrators" clause of FR Admin-03.

Both tiers are enforced server-side in `get_readonly_fields` and the
`has_*_permission` hooks, so hiding a widget is never the only thing standing
between an account and an escalation (NFR-10).
"""

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.core.admin import ExportCsvMixin

from .models import Customer, StaffRole, WishlistItem

#: Fields that hand out privilege. Editable by superusers only.
PRIVILEGE_FIELDS = ("role", "is_staff", "is_superuser", "groups", "user_permissions")

#: Declared field order, used to keep `get_readonly_fields` output deterministic.
_FIELD_ORDER = (
    "email",
    "name",
    "phone",
    "addresses",
    *PRIVILEGE_FIELDS,
    "is_active",
    "last_login",
    "date_joined",
)


@admin.register(Customer)
class CustomerAdmin(BaseUserAdmin, ExportCsvMixin):
    """Admin for the custom Customer user model (email-based, no username)."""

    # Override BaseUserAdmin fields that reference 'username' which doesn't exist.
    ordering = ("-date_joined",)
    list_display = (
        "email",
        "name",
        "phone",
        "role",
        "console_display",
        "is_active",
        "date_joined",
    )
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "name", "phone")
    actions = ["activate_accounts", "suspend_accounts", "export_as_csv"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("name", "phone", "addresses")}),
        (
            "Console access",
            {
                "fields": ("role", "is_staff", "is_superuser"),
                "description": "<code>role</code> chooses the console; "
                "<code>is_staff</code> is the gate that makes it effective. "
                "Clearing staff status revokes console access without discarding "
                "which console the account belonged to.",
            },
        ),
        ("Status", {"fields": ("is_active",)}),
        ("Permissions", {"fields": ("groups", "user_permissions"), "classes": ("collapse",)}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "name", "password1", "password2"),
            },
        ),
        (
            "Console access",
            {
                "classes": ("wide",),
                "fields": ("role", "is_staff"),
                "description": "Leave as Customer for shoppers. Merchant and "
                "Administrator both require staff status.",
            },
        ),
    )

    @admin.display(description="Console", ordering="role")
    def console_display(self, obj):
        """Which console this account can actually enter, right now.

        `role` alone is misleading: an inactive or non-staff account with the
        Administrator role opens nothing. This column reports the effective
        answer, so a suspended administrator is visibly powerless in the list.
        """
        console = obj.console
        if console is None:
            return "— storefront only"
        label = StaffRole(console).label
        return f"{label} (superuser)" if obj.is_superuser else label

    def get_readonly_fields(self, request, obj=None):
        """Lock privilege fields for non-superusers, and self-demotion for everyone.

        Returning them as read-only rather than dropping them from the form keeps
        the values visible — an administrator investigating an account still
        needs to see that it is a merchant, just not be able to change it.
        """
        readonly = {"date_joined", "last_login", *super().get_readonly_fields(request, obj)}
        if not request.user.is_superuser:
            readonly.update(PRIVILEGE_FIELDS)
        if obj is not None and obj.pk == request.user.pk:
            # Self-lockout guard: nobody edits their own way out of the console
            # they are currently signed in to. Undoing that needs shell access.
            readonly.update({"is_active", *PRIVILEGE_FIELDS})
        return tuple(field for field in _FIELD_ORDER if field in readonly)

    def has_change_permission(self, request, obj=None):
        """A non-superuser administrator may not edit a superuser.

        Without this, an administrator could reset the password of the account
        that outranks them and inherit its privileges — the classic horizontal
        escalation through an account-management screen.
        """
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        if obj is not None and obj.pk == request.user.pk:
            return False
        return super().has_delete_permission(request, obj)

    @admin.action(description="Activate selected accounts")
    def activate_accounts(self, request, queryset):
        self._set_active(request, queryset, True)

    @admin.action(description="Suspend selected accounts (ends their sessions)")
    def suspend_accounts(self, request, queryset):
        self._set_active(request, queryset, False)

    def _set_active(self, request, queryset, active):
        """Flip is_active and record each change in the audit trail (FR Admin-05).

        Deliberately a per-row save rather than `queryset.update()`: a bulk
        UPDATE writes no LogEntry rows, and an account suspension that leaves no
        trace is exactly the event an audit trail exists to capture.

        Suspension takes effect on the next request, not at the next login —
        `ModelBackend.get_user` refuses an inactive user, so any live session for
        that account stops working immediately (FR Customer-21).
        """
        queryset = queryset.exclude(pk=request.user.pk)  # never suspend yourself
        if not request.user.is_superuser:
            # An administrator who cannot edit a superuser individually must not
            # be able to suspend one in bulk either.
            queryset = queryset.exclude(is_superuser=True)

        changed = 0
        for account in queryset.exclude(is_active=active):
            account.is_active = active
            account.save(update_fields=["is_active"])
            self.log_change(request, account, "Activated." if active else "Suspended.")
            changed += 1

        verb = "Activated" if active else "Suspended"
        self.message_user(request, f"{verb} {changed} account(s).")


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("customer", "product", "created_at")
    search_fields = ("customer__email", "product__name")
    readonly_fields = ("customer", "product", "created_at")

    def get_queryset(self, request):
        # Both list columns dereference a FK; without this the changelist issues
        # two extra queries per row.
        return super().get_queryset(request).select_related("customer", "product")

    def has_add_permission(self, request):
        # Wishlist items are managed by the storefront, not the admin.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LogEntry)
class AuditTrailAdmin(admin.ModelAdmin):
    """FR Admin-05: the record of what back-office staff actually did.

    Django writes a LogEntry for every add, change, and delete performed through
    *either* console, so this one screen covers merchant activity as well as
    administrator activity. It is registered on the administrator console only —
    letting merchants read, edit, or prune the log of their own actions would
    defeat the point.

    Fully read-only: no add, no change, no delete, for anyone, superusers
    included. The trail is append-only by construction, the same guarantee
    `StockMovement` gives the stock ledger.
    """

    date_hierarchy = "action_time"
    list_display = ("action_time", "user", "action_description", "content_type", "object_repr")
    list_filter = ("action_flag", "content_type", "action_time")
    search_fields = ("object_repr", "change_message", "user__email")
    ordering = ("-action_time",)
    list_select_related = ("user", "content_type")

    @admin.display(description="Action", ordering="action_flag")
    def action_description(self, obj):
        """Render the numeric action_flag as the word an auditor is looking for."""
        return {1: "Added", 2: "Changed", 3: "Deleted"}.get(obj.action_flag, "Unknown")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
