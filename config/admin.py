"""Admin app configuration.

Replacing `django.contrib.admin` with `config.admin.MetroDripAdminConfig` in
INSTALLED_APPS makes `admin.site` resolve to `AdministratorSite`, so every
`admin.site.register(...)` call and `admin.site.urls` keeps working — the
administrator console simply *is* Django's default site.

`default_site` is a dotted path rather than an import because this module is
loaded during `apps.populate()`, before models exist. Django resolves the string
in `AdminConfig.ready()`, by which point `config.consoles` can safely import
`apps.accounts.roles`.

The merchant console is a second, non-default site — see `config/consoles.py`.
"""

from django.contrib.admin.apps import AdminConfig


class MetroDripAdminConfig(AdminConfig):
    """Point Django's admin app at the administrator console."""

    default_site = "config.consoles.AdministratorSite"
