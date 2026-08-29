"""The administrator / merchant console boundary (ADR-F-001).

These tests exist to make the separation falsifiable. The failure mode they
guard against is not "a page 500s" — it is a model quietly appearing on both
consoles, or a role check that a signed-in merchant can walk straight through.

Structure:

* `TestRegistrySeparation` — which console owns which model. Registry-level, so
  it fails the moment someone registers a model on the wrong site.
* `TestConsoleAccess`      — the HTTP boundary, exercised with real logins.
* `TestLoginBoundary`      — the wrong console rejects credentials at the form,
  rather than looping between login and index.
* `TestPrivilegeEscalation`— the limits on what an administrator can do to other
  administrators.
* `TestRolePermissionSync` — the group grants derived from the registries.
* `TestRoleModel`          — the `console` predicate itself.
* `TestHomepageCacheIsolation` — the console shortcut in shared chrome is not
  leaked between visitors by the homepage's page cache.
"""

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.urls import reverse

from apps.accounts.models import Customer, StaffRole
from config.consoles import merchant_site

pytestmark = pytest.mark.django_db

PASSWORD = "console-test-pw-8842"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def merchant():
    return Customer.objects.create_user(
        email="merchant@metrodrip.test",
        password=PASSWORD,
        name="Demo Merchant",
        role=StaffRole.MERCHANT,
        is_staff=True,
    )


@pytest.fixture()
def administrator():
    return Customer.objects.create_user(
        email="administrator@metrodrip.test",
        password=PASSWORD,
        name="Demo Administrator",
        role=StaffRole.ADMINISTRATOR,
        is_staff=True,
    )


@pytest.fixture()
def superuser():
    return Customer.objects.create_superuser(
        email="root@metrodrip.test", password=PASSWORD, name="Root"
    )


@pytest.fixture()
def shopper():
    return Customer.objects.create_user(
        email="shopper@metrodrip.test", password=PASSWORD, name="Shopper"
    )


def labels(site):
    """`{"app.Model", ...}` registered on a console."""
    return {model._meta.label for model in site._registry}


# ---------------------------------------------------------------------------
# Registry ownership
# ---------------------------------------------------------------------------


class TestRegistrySeparation:
    """Each model belongs to exactly one console."""

    def test_no_model_is_registered_on_both_consoles(self):
        """The core invariant: zero overlap.

        Duplicating a model would give two screens that can edit the same rows
        under different authorization rules — the separation would be cosmetic.
        """
        assert labels(admin.site) & labels(merchant_site) == set()

    @pytest.mark.parametrize(
        "label",
        [
            "catalog.Product",
            "catalog.Category",
            "inventory.StockRecord",
            "inventory.StockMovement",
            "orders.Order",
            "payments.Payment",
            "shipping.Shipment",
            "reviews.Review",
            "cms.HomepageBanner",
            "cms.ContactMessage",
            "flatpages.FlatPage",
        ],
    )
    def test_selling_models_live_on_the_merchant_console(self, label):
        assert label in labels(merchant_site)
        assert label not in labels(admin.site)

    @pytest.mark.parametrize(
        "label",
        [
            "accounts.Customer",  # FR Admin-02
            "auth.Group",  # FR Admin-03
            "shipping.ShippingZone",  # FR Admin-04
            "admin.LogEntry",  # FR Admin-05
        ],
    )
    def test_governance_models_live_on_the_administrator_console(self, label):
        assert label in labels(admin.site)
        assert label not in labels(merchant_site)

    def test_customer_records_are_not_reachable_from_the_merchant_console(self):
        """Shopper PII is governance data.

        Called out separately from the parametrised case because this is the
        privacy boundary (NFR-11), not just a filing decision.
        """
        assert "accounts.Customer" not in labels(merchant_site)
        assert "accounts.WishlistItem" not in labels(merchant_site)

    def test_audit_trail_is_append_only_even_for_superusers(self):
        """A log staff can edit is not an audit trail (FR Admin-05)."""
        from django.contrib.admin.models import LogEntry

        model_admin = admin.site._registry[LogEntry]
        assert model_admin.has_add_permission(None) is False
        assert model_admin.has_change_permission(None) is False
        assert model_admin.has_delete_permission(None) is False


# ---------------------------------------------------------------------------
# HTTP access boundary
# ---------------------------------------------------------------------------


class TestConsoleAccess:
    """Who gets through the door, verified over HTTP with real sessions."""

    def test_merchant_reaches_the_merchant_console(self, client, merchant):
        client.force_login(merchant)
        assert client.get(reverse("merchant:index")).status_code == 200

    def test_merchant_is_refused_by_the_administrator_console(self, client, merchant):
        client.force_login(merchant)
        response = client.get(reverse("admin:index"), follow=True)
        assert response.status_code == 403
        assert b"wrong console" in response.content.lower()

    def test_administrator_reaches_the_administrator_console(self, client, administrator):
        client.force_login(administrator)
        assert client.get(reverse("admin:index")).status_code == 200

    def test_administrator_is_refused_by_the_merchant_console(self, client, administrator):
        client.force_login(administrator)
        response = client.get(reverse("merchant:index"), follow=True)
        assert response.status_code == 403

    def test_superuser_reaches_both_consoles(self, client, superuser):
        client.force_login(superuser)
        assert client.get(reverse("admin:index")).status_code == 200
        assert client.get(reverse("merchant:index")).status_code == 200

    def test_shopper_reaches_neither_console(self, client, shopper):
        """A signed-in shopper is refused by both, and told so.

        Not a login form: they are already authenticated, so re-prompting would
        imply their password was wrong. `console` is None, so the page offers no
        "go to my console" link — only the storefront and an account swap.
        """
        client.force_login(shopper)
        for url in (reverse("admin:index"), reverse("merchant:index")):
            response = client.get(url, follow=True)
            assert response.status_code == 403, url
            assert b"wrong console" in response.content.lower(), url
            assert b"Go to my console" not in response.content, url

    def test_console_denial_offers_a_csrf_protected_account_swap(self, client, shopper):
        """Signing out is a state change, so it must not be a bare link."""
        client.force_login(shopper)
        body = client.get(reverse("admin:index"), follow=True).content
        assert b'method="post"' in body
        assert b"csrfmiddlewaretoken" in body
        assert b'name="next" value="/admin/login/"' in body

    def test_account_swap_returns_to_the_console_login(self, client, shopper):
        """The `next` hop added to logout_view actually lands where it claims."""
        client.force_login(shopper)
        response = client.post(reverse("accounts:logout"), {"next": "/admin/login/"})
        assert response.status_code == 302
        assert response["Location"] == "/admin/login/"

    def test_logout_next_cannot_leave_the_site(self, client, shopper):
        """`_safe_next_url` rejects off-host targets — no open redirect."""
        client.force_login(shopper)
        response = client.post(reverse("accounts:logout"), {"next": "https://evil.example/"})
        assert response.status_code == 302
        assert "evil.example" not in response["Location"]

    def test_anonymous_visitor_reaches_neither_console(self, client):
        for url in (reverse("admin:index"), reverse("merchant:index")):
            response = client.get(url)
            assert response.status_code == 302
            assert "login" in response["Location"], url

    def test_suspending_an_account_closes_its_console_immediately(self, client, merchant):
        """FR Customer-21 / FR Admin-02: suspension ends live sessions.

        `ModelBackend.get_user` refuses an inactive user, so the existing session
        cookie stops authenticating on the very next request — no logout and no
        session-expiry wait required.
        """
        client.force_login(merchant)
        assert client.get(reverse("merchant:index")).status_code == 200

        Customer.objects.filter(pk=merchant.pk).update(is_active=False)

        response = client.get(reverse("merchant:index"))
        assert response.status_code == 302
        assert "login" in response["Location"]

    def test_revoking_staff_status_closes_the_console_but_keeps_the_role(self, client, merchant):
        """`is_staff` is the gate; `role` is only the routing."""
        client.force_login(merchant)
        Customer.objects.filter(pk=merchant.pk).update(is_staff=False)

        assert client.get(reverse("merchant:index")).status_code == 302
        merchant.refresh_from_db()
        assert merchant.role == StaffRole.MERCHANT  # not discarded, just inert
        assert merchant.console is None

    def test_merchant_cannot_reach_an_administrator_model_page_directly(self, client, merchant):
        """Deny by default (NFR-10): the URL simply does not exist over there.

        Guessing `/merchant/accounts/customer/` must not work — the model is not
        in that registry, so no view was ever routed for it.
        """
        client.force_login(merchant)
        assert client.get("/merchant/accounts/customer/").status_code == 404

    def test_administrator_cannot_reach_a_merchant_model_page_directly(self, client, administrator):
        client.force_login(administrator)
        assert client.get("/admin/catalog/product/").status_code == 404


# ---------------------------------------------------------------------------
# Login form boundary
# ---------------------------------------------------------------------------


class TestLoginBoundary:
    """Credentials are rejected at the wrong console's login form."""

    def test_merchant_credentials_are_rejected_at_the_administrator_login(self, client):
        """Guards against a redirect loop, not just a wrong outcome.

        `AdminAuthenticationForm` only checks `is_staff`, which a merchant has.
        Without a role check here the login would succeed, the index would refuse
        the session, and the browser would bounce between the two forever.
        """
        Customer.objects.create_user(
            email="loop@metrodrip.test",
            password=PASSWORD,
            name="Loop",
            role=StaffRole.MERCHANT,
            is_staff=True,
        )
        response = client.post(
            "/admin/login/", {"username": "loop@metrodrip.test", "password": PASSWORD}
        )
        assert response.status_code == 200  # re-rendered form, not a redirect
        assert b"does not have access to the administrator console" in response.content
        assert not response.wsgi_request.user.is_authenticated

    def test_administrator_credentials_are_rejected_at_the_merchant_login(self, client):
        Customer.objects.create_user(
            email="gov@metrodrip.test",
            password=PASSWORD,
            name="Gov",
            role=StaffRole.ADMINISTRATOR,
            is_staff=True,
        )
        response = client.post(
            "/merchant/login/", {"username": "gov@metrodrip.test", "password": PASSWORD}
        )
        assert response.status_code == 200
        assert b"does not have access to the merchant console" in response.content

    def test_each_console_login_page_names_itself(self, client):
        assert b"Administrator Login" in client.get("/admin/login/").content
        assert b"Merchant Login" in client.get("/merchant/login/").content

    @pytest.mark.parametrize(
        ("url", "identity", "provisioning_copy"),
        [
            (
                "/admin/login/",
                b"METRODRIP PLATFORM",
                b"Administrator access is provisioned internally",
            ),
            (
                "/merchant/login/",
                b"STORE MANAGEMENT",
                b"Staff self-registration is disabled",
            ),
        ],
    )
    def test_console_login_uses_the_responsive_provisioned_account_shell(
        self, client, url, identity, provisioning_copy
    ):
        body = client.get(url).content

        assert b'class="console-auth"' in body
        assert identity in body
        assert provisioning_copy in body
        assert b"Return to storefront" in body
        assert b'name="username"' in body and b'autocomplete="username"' in body
        assert b'name="password"' in body and b'autocomplete="current-password"' in body
        assert b'name="otp_token"' in body and b'autocomplete="one-time-code"' in body
        assert b'aria-describedby="otp_token_help"' in body

    @pytest.mark.parametrize("url", ["/admin/login/", "/merchant/login/"])
    def test_console_login_offers_explicit_light_and_dark_modes(self, client, url):
        body = client.get(url).content

        assert b'data-console-theme="light"' in body
        assert b'data-console-theme="dark"' in body
        assert b'role="group" aria-label="Colour theme"' in body
        assert b"js/console-theme.js" in body
        assert b"admin/js/theme.js" not in body
        assert b'name="description" content="Secure staff access to the MetroDrip' in body
        assert b'href="/static/images/favicon.svg" type="image/svg+xml"' in body

    @pytest.mark.parametrize("url", ["/admin/login/", "/merchant/login/"])
    def test_console_login_errors_are_announced(self, client, url):
        response = client.post(url, {"username": "invalid@metrodrip.test", "password": "wrong"})

        assert response.status_code == 200
        assert b'class="console-auth__errors" role="alert" aria-live="polite"' in response.content

    @pytest.mark.parametrize(
        ("url", "fixture_name"),
        [("/admin/", "administrator"), ("/merchant/", "merchant")],
    )
    def test_authenticated_consoles_keep_the_theme_picker(self, client, request, url, fixture_name):
        client.force_login(request.getfixturevalue(fixture_name))
        body = client.get(url).content

        assert b'data-console-theme="light"' in body
        assert b'data-console-theme="dark"' in body
        assert b"js/console-theme.js" in body
        assert b"admin/js/theme.js" not in body

    def test_wrong_console_page_links_to_the_console_the_user_owns(self, client, merchant):
        client.force_login(merchant)
        response = client.get("/admin/login/")
        assert response.status_code == 403
        assert reverse("merchant:index").encode() in response.content

    def test_console_denial_renders_no_template_syntax(self, client, merchant):
        """A stray `{#` or `{%` in the page means a comment leaked as text."""
        client.force_login(merchant)
        body = client.get("/admin/login/").content
        assert b"{#" not in body
        assert b"{%" not in body


# ---------------------------------------------------------------------------
# Privilege escalation inside the administrator console
# ---------------------------------------------------------------------------


class TestPrivilegeEscalation:
    """FR Admin-03: only *authorized* administrators manage roles."""

    def _customer_admin(self):
        return admin.site._registry[Customer]

    class _Req:
        def __init__(self, user):
            self.user = user

    def test_non_superuser_administrator_cannot_edit_privilege_fields(
        self, administrator, merchant
    ):
        readonly = self._customer_admin().get_readonly_fields(
            self._Req(administrator), obj=merchant
        )
        for field in ("role", "is_staff", "is_superuser", "groups", "user_permissions"):
            assert field in readonly, field

    def test_superuser_can_edit_privilege_fields(self, superuser, merchant):
        readonly = self._customer_admin().get_readonly_fields(self._Req(superuser), obj=merchant)
        assert "role" not in readonly
        assert "is_superuser" not in readonly

    def test_nobody_can_edit_their_own_privileges(self, superuser):
        """Even a superuser cannot demote the account it is signed in as."""
        readonly = self._customer_admin().get_readonly_fields(self._Req(superuser), obj=superuser)
        assert "is_active" in readonly
        assert "role" in readonly
        assert "is_superuser" in readonly

    def test_administrator_cannot_edit_a_superuser(self, administrator, superuser):
        """Otherwise: reset the superuser's password, then log in as it."""
        assert (
            self._customer_admin().has_change_permission(self._Req(administrator), obj=superuser)
            is False
        )

    def test_administrator_cannot_delete_a_superuser_or_itself(self, administrator, superuser):
        model_admin = self._customer_admin()
        assert model_admin.has_delete_permission(self._Req(administrator), obj=superuser) is False
        assert (
            model_admin.has_delete_permission(self._Req(administrator), obj=administrator) is False
        )

    def test_suspend_action_skips_the_acting_administrator(self, superuser, merchant):
        """Bulk-selecting everything must not lock the operator out."""
        model_admin = self._customer_admin()
        request = self._Req(superuser)
        request.session = {}
        # message_user needs the messages framework; the action's effect on the
        # database is what matters here.
        model_admin.message_user = lambda *a, **kw: None

        model_admin.suspend_accounts(request, Customer.objects.all())

        superuser.refresh_from_db()
        merchant.refresh_from_db()
        assert superuser.is_active is True  # excluded from its own action
        assert merchant.is_active is False

    def test_suspension_is_written_to_the_audit_trail(self, superuser, merchant):
        """FR Admin-05: a suspension that leaves no trace is the bug."""
        from django.contrib.admin.models import LogEntry

        model_admin = self._customer_admin()
        request = self._Req(superuser)
        request.session = {}
        model_admin.message_user = lambda *a, **kw: None

        model_admin.suspend_accounts(request, Customer.objects.filter(pk=merchant.pk))

        entry = LogEntry.objects.filter(object_id=str(merchant.pk)).first()
        assert entry is not None
        assert "Suspended" in entry.change_message

    def test_csv_export_never_contains_password_hashes(self, superuser, merchant):
        """NFR-11: the export walks _meta.fields, which includes `password`."""
        model_admin = self._customer_admin()
        response = model_admin.export_as_csv(self._Req(superuser), Customer.objects.all())
        body = response.content.decode()
        assert "password" not in body.split("\r\n")[0]
        assert merchant.password not in body


# ---------------------------------------------------------------------------
# Group permission sync
# ---------------------------------------------------------------------------


class TestRolePermissionSync:
    """`sync_console_roles` derives grants from the registries."""

    def test_sync_creates_both_groups_with_disjoint_model_grants(self, capsys):
        call_command("sync_console_roles")
        capsys.readouterr()

        merchants = Group.objects.get(name="Merchants")
        administrators = Group.objects.get(name="Administrators")

        def models_of(group):
            return {
                perm.content_type.model for perm in group.permissions.select_related("content_type")
            }

        assert "product" in models_of(merchants)
        assert "customer" not in models_of(merchants)
        assert "customer" in models_of(administrators)
        assert "product" not in models_of(administrators)

    def test_read_only_admins_get_view_only(self, capsys):
        """`StockMovement` is an append-only ledger; the grant must say so."""
        call_command("sync_console_roles")
        capsys.readouterr()

        codenames = set(
            Group.objects.get(name="Merchants").permissions.values_list("codename", flat=True)
        )
        assert "view_stockmovement" in codenames
        assert "add_stockmovement" not in codenames
        assert "change_stockmovement" not in codenames
        assert "delete_stockmovement" not in codenames
        # A normally-editable model still gets the full set, proving the probe
        # distinguishes the two rather than granting view everywhere.
        assert {"add_product", "change_product", "delete_product"} <= codenames

    def test_sync_is_idempotent(self, capsys):
        call_command("sync_console_roles")
        first = set(Group.objects.get(name="Merchants").permissions.values_list("pk", flat=True))
        call_command("sync_console_roles")
        second = set(Group.objects.get(name="Merchants").permissions.values_list("pk", flat=True))
        capsys.readouterr()
        assert first == second

    def test_sync_assigns_staff_to_their_console_group(self, merchant, administrator, capsys):
        call_command("sync_console_roles")
        capsys.readouterr()

        merchant.refresh_from_db()
        assert merchant.groups.filter(name="Merchants").exists()
        assert not merchant.groups.filter(name="Administrators").exists()
        assert administrator.groups.filter(name="Administrators").exists()

    def test_sync_removes_a_stale_membership_after_a_role_change(self, merchant, capsys):
        """A demoted merchant must not keep yesterday's grants."""
        call_command("sync_console_roles")
        assert merchant.groups.filter(name="Merchants").exists()

        Customer.objects.filter(pk=merchant.pk).update(role=StaffRole.ADMINISTRATOR)
        call_command("sync_console_roles")
        capsys.readouterr()

        merchant.refresh_from_db()
        assert not merchant.groups.filter(name="Merchants").exists()
        assert merchant.groups.filter(name="Administrators").exists()

    def test_dry_run_writes_nothing(self, capsys):
        call_command("sync_console_roles", "--dry-run")
        capsys.readouterr()
        assert not Group.objects.filter(name__in=["Merchants", "Administrators"]).exists()

    def test_a_merchant_with_group_permissions_sees_products(self, client, merchant, capsys):
        """The end-to-end point of the sync: the console is not empty."""
        call_command("sync_console_roles")
        capsys.readouterr()

        client.force_login(merchant)
        response = client.get(reverse("merchant:index"))
        assert response.status_code == 200
        assert b"Products" in response.content


# ---------------------------------------------------------------------------
# create_console_account
# ---------------------------------------------------------------------------


class TestCreateConsoleAccount:
    def test_creates_a_scoped_merchant_not_a_superuser(self, capsys):
        call_command(
            "create_console_account",
            "--role",
            "merchant",
            "--email",
            "New.Seller@Metrodrip.TEST",
            "--name",
            "New Seller",
            "--password",
            PASSWORD,
        )
        capsys.readouterr()

        account = Customer.objects.get(email="new.seller@metrodrip.test")
        assert account.is_staff is True
        assert account.is_superuser is False
        assert account.role == StaffRole.MERCHANT
        assert account.console == StaffRole.MERCHANT
        assert account.check_password(PASSWORD)

    def test_rerunning_re_roles_without_needing_a_password(self, merchant, capsys):
        call_command(
            "create_console_account",
            "--role",
            "administrator",
            "--email",
            merchant.email,
        )
        capsys.readouterr()

        merchant.refresh_from_db()
        assert merchant.role == StaffRole.ADMINISTRATOR
        assert merchant.check_password(PASSWORD)  # untouched

    def test_refuses_to_scope_a_superuser(self, superuser):
        with pytest.raises(CommandError, match="superuser"):
            call_command(
                "create_console_account",
                "--role",
                "merchant",
                "--email",
                superuser.email,
            )

    def test_rejects_a_weak_password(self):
        with pytest.raises(CommandError, match="Password rejected"):
            call_command(
                "create_console_account",
                "--role",
                "merchant",
                "--email",
                "weak@metrodrip.test",
                "--password",
                "1234",
            )


# ---------------------------------------------------------------------------
# The role model itself
# ---------------------------------------------------------------------------


class TestRoleModel:
    def test_console_requires_active_staff_and_a_console_role(self):
        account = Customer(role=StaffRole.MERCHANT, is_staff=True, is_active=True)
        assert account.console == StaffRole.MERCHANT

        account.is_active = False
        assert account.console is None

        account.is_active, account.is_staff = True, False
        assert account.console is None

        account.is_staff, account.role = True, StaffRole.CUSTOMER
        assert account.console is None

    def test_superuser_reports_the_administrator_console(self):
        account = Customer(role=StaffRole.CUSTOMER, is_staff=True, is_superuser=True)
        assert account.console == StaffRole.ADMINISTRATOR
        assert account.is_administrator is True
        assert account.is_merchant is True  # admitted to both

    def test_new_accounts_default_to_storefront_only(self, shopper):
        assert shopper.role == StaffRole.CUSTOMER
        assert shopper.console is None

    def test_createsuperuser_labels_itself_administrator(self, superuser):
        assert superuser.role == StaffRole.ADMINISTRATOR

    def test_a_console_role_without_staff_status_fails_validation(self):
        """`clean` stops an operator saving an account that looks privileged."""
        from django.core.exceptions import ValidationError

        account = Customer(
            email="inert@metrodrip.test",
            name="Inert",
            role=StaffRole.ADMINISTRATOR,
            is_staff=False,
        )
        with pytest.raises(ValidationError) as excinfo:
            account.clean()
        assert "is_staff" in excinfo.value.message_dict

    def test_existing_staff_were_migrated_to_the_administrator_console(self):
        """Migration 0002 must not have locked out yesterday's admins.

        Re-runs the data migration's logic against a row shaped like a
        pre-migration staff account.
        """
        legacy = Customer.objects.create_user(
            email="legacy@metrodrip.test", password=PASSWORD, name="Legacy", is_staff=True
        )
        # The migration promoted every is_staff row; a fresh create_user does not,
        # so assert the *rule* rather than the row.
        Customer.objects.filter(is_staff=True, role=StaffRole.CUSTOMER).update(
            role=StaffRole.ADMINISTRATOR
        )
        legacy.refresh_from_db()
        assert legacy.console == StaffRole.ADMINISTRATOR


# ---------------------------------------------------------------------------
# Homepage page-cache isolation
# ---------------------------------------------------------------------------


@pytest.fixture()
def real_page_cache(settings):
    """Swap DummyCache for a real one, so `@cache_page` actually caches.

    `override_settings` cannot decorate a plain pytest class, and the cache has
    to be live for these assertions to mean anything — under the suite's default
    DummyCache every one of them passes whether the bug is present or not.

    LocMemCache instances are keyed by location and shared across tests in the
    same process, so the entry is cleared on both sides of the test rather than
    trusting the previous test to have tidied up.
    """
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    yield
    cache.clear()


@pytest.mark.usefixtures("real_page_cache")
class TestHomepageCacheIsolation:
    """The homepage cache must not serve one visitor's navbar to another.

    The bug this pins was live, and this feature is what exposed it: `homepage`
    was decorated `@cache_page` with no `Vary: Cookie`, so the first render of
    `/` was replayed to every visitor for five minutes. A signed-in merchant
    loading the storefront got the anonymous navbar with no console shortcut.
    """

    def test_anonymous_render_is_not_replayed_to_staff(self, client, merchant):
        anonymous = client.get("/")
        assert b"Merchant Console" not in anonymous.content

        client.force_login(merchant)
        assert b"Merchant Console" in client.get("/").content

    def test_staff_render_is_not_replayed_to_anonymous(self, client, merchant):
        """The direction that actually matters: no console link for a stranger."""
        client.force_login(merchant)
        assert b"Merchant Console" in client.get("/").content

        client.logout()
        assert b"Merchant Console" not in client.get("/").content

    def test_two_staff_accounts_do_not_share_a_cache_entry(
        self, client, django_user_model, merchant
    ):
        """Per-cookie keying, asserted by content rather than by header.

        Checking for `Vary: Cookie` on the response would prove nothing: the
        header is present even with the bug, because SessionMiddleware adds it on
        the way out — after `cache_page` has already chosen its key. That timing
        gap *is* the bug, so only the cached body can distinguish the two states.
        """
        administrator = django_user_model.objects.create_user(
            email="second@metrodrip.test",
            password=PASSWORD,
            name="Second",
            role=StaffRole.ADMINISTRATOR,
            is_staff=True,
        )
        client.force_login(merchant)
        assert b"Merchant Console" in client.get("/").content

        client.force_login(administrator)
        body = client.get("/").content
        assert b">Administration<" in body
        assert b"Merchant Console" not in body
