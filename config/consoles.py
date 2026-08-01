"""The two back-office consoles.

MetroDrip runs two independent Django admin sites rather than one:

    /admin/      AdministratorSite  — accounts, roles, platform settings, audit
    /merchant/   MerchantSite       — catalog, stock, orders, content, reviews

Each model is registered on exactly one of them (see DECISIONS.md ADR-F-001), so
"which console owns this?" has a single answer that lives next to the model
rather than in a permissions spreadsheet. A merchant who reaches `/admin/` is
refused before any view runs, and vice versa.

Why two sites and not one site plus permissions: Django's app-list index is built
from the *registry*, not from permissions, so a single site would still render
"Accounts", "Shipping Zones" and "Audit Trail" headings to a merchant with an
empty table under each. Separate registries mean each console only ever knows
about its own models — the boundary is structural, not cosmetic.

Both consoles remain permission-checked per model on top of the role gate, so a
merchant account with no group still sees an empty console (NFR-10, deny by
default). `sync_console_roles` grants the matching group permissions.
"""

from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.accounts.roles import StaffRole

#: Console role -> URL instance namespace, used to point a signed-in user at the
#: console they *do* own when they land on the wrong one.
CONSOLE_NAMESPACE = {
    StaffRole.ADMINISTRATOR: "admin",
    StaffRole.MERCHANT: "merchant",
}


class ConsoleAuthenticationForm(AdminAuthenticationForm):
    """Admin login form that also enforces the console's role.

    Without this, `/admin/login/` would accept a merchant's credentials (they
    are `is_staff`, which is all `AdminAuthenticationForm` checks), redirect to
    the index, be refused by `has_permission`, and bounce straight back to the
    login page — an endless loop with no explanation. Rejecting at the form
    turns that into one clear error message.
    """

    console_role = None
    console_label = "this console"

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)  # is_active, then is_staff
        if user.is_superuser or user.role == self.console_role:
            return
        raise ValidationError(
            "This account does not have access to the %(console)s. "
            "Please sign in with an account for this console.",
            code="wrong_console",
            params={"console": self.console_label},
        )


class AdministratorAuthenticationForm(ConsoleAuthenticationForm):
    console_role = StaffRole.ADMINISTRATOR
    console_label = "administrator console"


class MerchantAuthenticationForm(ConsoleAuthenticationForm):
    console_role = StaffRole.MERCHANT
    console_label = "merchant console"


class ConsoleSite(admin.AdminSite):
    """An admin site scoped to one back-office role."""

    #: The role, besides superuser, that this console admits.
    console_role = None
    #: Heading shown on the login page only (see `login`).
    login_heading = "Sign in"
    #: Human name used in denial messages.
    console_label = "console"

    def has_permission(self, request):
        """Server-side gate for every view on this console (NFR-10).

        Overrides Django's `is_active and is_staff` check to also require the
        console's role. Anonymous users fail on `is_active`, so the `role` lookup
        is never reached for them — `getattr` guards it anyway, because
        `AnonymousUser` has no such attribute.
        """
        user = request.user
        if not (user.is_active and user.is_staff):
            return False
        return bool(user.is_superuser) or getattr(user, "role", None) == self.console_role

    def each_context(self, request):
        """Add the console identity every admin template can branch on."""
        context = super().each_context(request)
        context["console_role"] = self.console_role
        context["console_label"] = self.console_label
        return context

    def login(self, request, extra_context=None):
        """Render the login page, or explain a wrong-console landing.

        Two distinct cases arrive here:

        1. Nobody is signed in — show the login form under this console's own
           heading. `AdminSite.login` applies `extra_context` after
           `each_context`, so setting `site_header` here retitles the login page
           without also retitling logout and password-reset, which overriding
           `each_context` would.
        2. Somebody *is* signed in but belongs to the other console —
           `admin_view` bounced them here. Re-showing a login form implies their
           credentials were wrong; they were not. Say what actually happened and
           link to the console they own.
        """
        if request.user.is_authenticated and not self.has_permission(request):
            return self.render_wrong_console(request)
        return super().login(
            request,
            {**(extra_context or {}), "site_header": self.login_heading},
        )

    def render_wrong_console(self, request):
        """403 page naming the console the signed-in user actually owns."""
        own_console = getattr(request.user, "console", None)
        own_url = None
        if own_console and own_console != self.console_role:
            try:
                own_url = reverse(f"{CONSOLE_NAMESPACE[own_console]}:index")
            except (NoReverseMatch, KeyError):  # pragma: no cover - defensive
                own_url = None
        return render(
            request,
            "admin/console_denied.html",
            {
                "title": "Wrong console",
                "requested_console": self.console_label,
                "own_console_label": StaffRole(own_console).label if own_console else None,
                "own_console_url": own_url,
                # Where "sign in as someone else" comes back to. This console's
                # own logout is unreachable from here — `admin_view` bounces a
                # permission-less request off it back to the index — so the swap
                # goes through the storefront logout and returns with `next`.
                "login_url": reverse(f"{self.name}:login"),
                "site_header": self.site_header,
            },
            status=403,
        )


class AdministratorSite(ConsoleSite):
    """Platform governance: accounts, roles, settings, audit trail."""

    console_role = StaffRole.ADMINISTRATOR
    console_label = "administrator console"
    login_heading = "Administrator Login"
    login_form = AdministratorAuthenticationForm
    site_header = "MetroDrip Administration"
    site_title = "MetroDrip Administration"
    index_title = "Platform administration"
    index_template = "admin/index.html"


class MerchantSite(ConsoleSite):
    """Day-to-day selling: catalog, stock, orders, content, reviews."""

    console_role = StaffRole.MERCHANT
    console_label = "merchant console"
    login_heading = "Merchant Login"
    login_form = MerchantAuthenticationForm
    site_header = "MetroDrip Merchant Console"
    site_title = "MetroDrip Merchant Console"
    index_title = "Store management"
    index_template = "merchant/index.html"


#: The administrator console. `AdminConfig.default_site` points at
#: `AdministratorSite`, so `django.contrib.admin.site` *is* that instance and
#: keeps the `admin:` URL namespace every existing template already reverses.
#: Exported under an explicit name so app modules read as a deliberate choice of
#: console rather than "the default one".
administrator_site = admin.site

#: The merchant console, mounted at /merchant/ in config/urls.py.
merchant_site = MerchantSite(name="merchant")
