"""Admin site branding.

Swapping `django.contrib.admin` for `config.admin.MetroDripAdminConfig` in
INSTALLED_APPS makes `admin.site` resolve to the site below, so every existing
`admin.site.register(...)` call and `admin.site.urls` keeps working unchanged.
"""

from django.contrib import admin
from django.contrib.admin.apps import AdminConfig


class MetroDripAdminSite(admin.AdminSite):
    """Default admin site with MetroDrip branding."""

    site_header = "MetroDrip Administration"
    site_title = "MetroDrip Administration"
    index_title = "Dashboard"

    def login(self, request, extra_context=None):
        """Render the login page under its own heading.

        `AdminSite.login` applies `extra_context` last, after `each_context`, so
        this overrides the site header for the login page only. Overriding
        `each_context` instead would also retitle logout and password-reset,
        which are unauthenticated too.
        """
        return super().login(
            request,
            {**(extra_context or {}), "site_header": "Administrator Login"},
        )


class MetroDripAdminConfig(AdminConfig):
    """Point Django's admin app at the branded site above."""

    default_site = "config.admin.MetroDripAdminSite"
