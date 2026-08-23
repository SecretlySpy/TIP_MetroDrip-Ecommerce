"""The two back-office consoles.

MetroDrip runs two independent Django admin sites rather than one:

    /admin/      AdministratorSite  — accounts, roles, platform settings, audit
    /merchant/   MerchantSite       — catalog, stock, orders, content, reviews

Each site's ``each_context`` injects dashboard data (KPI aggregates, recent
records) only when the request path is the console index. This avoids needless
queries on every admin page while keeping index templates free of hard-coded mock
data.

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

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django_otp import devices_for_user
from django_otp.forms import OTPAuthenticationFormMixin

from apps.accounts import login_throttle
from apps.accounts.roles import StaffRole

#: Console role -> URL instance namespace, used to point a signed-in user at the
#: console they *do* own when they land on the wrong one.
CONSOLE_NAMESPACE = {
    StaffRole.ADMINISTRATOR: "admin",
    StaffRole.MERCHANT: "merchant",
}


def _has_confirmed_device(user):
    """Whether `user` has at least one confirmed OTP device.

    `devices_for_user` yields a generator across every installed plugin, not a
    queryset, so this short-circuits on the first hit rather than materialising
    a list of every device the user owns.
    """
    return any(True for _ in devices_for_user(user, confirmed=True))


def otp_required_for(user):
    """Whether `user` must present a TOTP token to sign in (ADR-P3-029).

    Two independent triggers, and the first is the one that matters most:

    1. **The user has a confirmed device.** Enrolling is then irreversible from
       the attacker's side — a stolen password alone stops working the moment a
       device exists. Without this, 2FA would be advisory: anyone holding the
       password could simply decline to send a token.
    2. **`CONSOLE_REQUIRE_OTP` is on.** Blanket enforcement for the whole
       console, which is the launch posture once every staff account is
       enrolled.

    The flag defaults to off deliberately. Defaulting it on would mean the first
    deployment locks out every account that exists, including the superuser
    needed to enroll anyone — the control would have to be disabled to recover
    from it, which is a worse outcome than enabling it on a schedule. Enrol
    first, then flip it; `python manage.py check_console_otp` reports readiness.
    """
    if user is None:
        return False
    if _has_confirmed_device(user):
        return True
    return bool(getattr(settings, "CONSOLE_REQUIRE_OTP", False))


class ConsoleAuthenticationForm(OTPAuthenticationFormMixin, AdminAuthenticationForm):
    """Admin login form that enforces the console's role, 2FA, and rate limits.

    Without this, `/admin/login/` would accept a merchant's credentials (they
    are `is_staff`, which is all `AdminAuthenticationForm` checks), redirect to
    the index, be refused by `has_permission`, and bounce straight back to the
    login page — an endless loop with no explanation. Rejecting at the form
    turns that into one clear error message.
    """

    otp_device = forms.CharField(required=False, widget=forms.Select)
    otp_token = forms.CharField(
        required=False,
        label="Authentication code",
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )
    otp_challenge = forms.CharField(required=False)

    console_role = None
    console_label = "this console"

    def clean(self):
        """Authenticate, but refuse first if this login is locked out (ADR-P3-029).

        The lockout check runs *before* `super().clean()` so a locked-out
        attempt never reaches `authenticate()` — no password hash computed, no
        database read, and no timing difference between a real and a nonexistent
        account to measure.

        The error is deliberately the same shape as a wrong password. Saying
        "this account is locked" would confirm the username exists, turning the
        control into an account-enumeration oracle.
        """
        username = self.cleaned_data.get("username") or self.data.get("username") or ""

        if login_throttle.is_locked_out(username=username, request=self.request):
            raise ValidationError(
                "Too many failed sign-in attempts. Please try again later.",
                code="rate_limited",
            )

        try:
            cleaned = super().clean()
            # Second factor, after the password is known good. Running it only
            # for users who owe one keeps unenrolled staff working while making
            # enrollment a one-way door: once a device exists, the password on
            # its own is no longer a way in (ADR-P3-029).
            user = self.get_user()
            if otp_required_for(user):
                if not _has_confirmed_device(user):
                    # CONSOLE_REQUIRE_OTP is on and this account never enrolled.
                    # Refusing is the point of the flag, so say so plainly —
                    # this message is only ever shown after a correct password,
                    # so it reveals nothing to someone who does not have one.
                    raise ValidationError(
                        "This console requires two-factor authentication and no "
                        "device is enrolled on this account. Ask an administrator "
                        "to enroll a TOTP device for you.",
                        code="otp_enrollment_required",
                    )
                self.clean_otp(user)
        except ValidationError:
            # Covers a wrong password, a wrong TOTP token, and
            # `confirm_login_allowed` refusals alike: all are failed attempts to
            # get into this console, and an attacker who could probe one for
            # free would just use that one. In particular, counting bad tokens
            # here is what stops an attacker with a stolen password from
            # brute-forcing a six-digit code, which is only a million guesses.
            login_throttle.record_failure(username=username, request=self.request)
            raise

        login_throttle.clear(username=username, request=self.request)
        return cleaned

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

        The OTP check lives here rather than only in the login form because a
        session can outlive the state the form saw (ADR-P3-029): a user who was
        signed in *before* a device was enrolled for them would otherwise keep
        an unverified session for its full lifetime, which is precisely the
        window an enrollment is meant to close.
        """
        user = request.user
        if not (user.is_active and user.is_staff):
            return False
        if not (bool(user.is_superuser) or getattr(user, "role", None) == self.console_role):
            return False
        if otp_required_for(user):
            # `is_verified` is added by OTPMiddleware; `getattr` keeps the gate
            # closed rather than open if the middleware is ever removed.
            verify = getattr(user, "is_verified", None)
            return bool(verify and verify())
        return True

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

    def each_context(self, request):
        """Inject dashboard KPIs and recent audit entries on the index page."""
        context = super().each_context(request)
        # Only query on the admin index — not every changelist/change form.
        if request.path.rstrip("/") in ("/admin", ""):
            from django.contrib.admin.models import LogEntry

            from apps.accounts.models import Customer

            context["staff_count"] = Customer.objects.filter(is_staff=True, is_active=True).count()
            context["recent_logs"] = LogEntry.objects.select_related(
                "user", "content_type"
            ).order_by("-action_time")[:20]
        return context


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

    def each_context(self, request):
        """Inject dashboard KPIs and stock data on the merchant index page."""
        context = super().each_context(request)
        if request.path.rstrip("/") in ("/merchant", ""):
            from django.db.models import F
            from django.utils import timezone

            from apps.inventory.models import Reservation, StockRecord
            from apps.orders.models import Order

            stocks = (
                StockRecord.objects.select_related("variant", "variant__product")
                .annotate(available_units=F("qty_on_hand") - F("qty_reserved"))
                .order_by("available_units")[:20]
            )
            context["stock_records"] = stocks
            context["total_skus"] = StockRecord.objects.count()
            context["low_stock_count"] = (
                StockRecord.objects.annotate(available_units=F("qty_on_hand") - F("qty_reserved"))
                .filter(available_units__lte=F("low_stock_threshold"))
                .count()
            )
            context["active_reservations"] = Reservation.objects.filter(status="active").count()
            today = timezone.localdate()
            context["today_orders"] = Order.objects.filter(created_at__date=today).count()
        return context


#: The administrator console. `AdminConfig.default_site` points at
#: `AdministratorSite`, so `django.contrib.admin.site` *is* that instance and
#: keeps the `admin:` URL namespace every existing template already reverses.
#: Exported under an explicit name so app modules read as a deliberate choice of
#: console rather than "the default one".
administrator_site = admin.site

#: The merchant console, mounted at /merchant/ in config/urls.py.
merchant_site = MerchantSite(name="merchant")
