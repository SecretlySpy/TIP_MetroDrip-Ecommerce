"""A-1 smoke checks: the project must import and the DB config must honor
Hard Invariant 6 (MySQL backend, utf8mb4) before any feature work lands."""

from django.conf import settings


def test_settings_import():
    assert settings.DEFAULT_AUTO_FIELD == "django.db.models.BigAutoField"


def test_database_is_mysql_utf8mb4():
    db = settings.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.mysql"
    assert db["OPTIONS"]["charset"] == "utf8mb4"
    assert "INNODB" in db["OPTIONS"]["init_command"].upper()


def test_all_ten_apps_installed():
    expected = {
        "apps.catalog",
        "apps.inventory",
        "apps.orders",
        "apps.payments",
        "apps.shipping",
        "apps.notifications",
        "apps.accounts",
        "apps.reviews",
        "apps.cms",
        "apps.storefront",
    }
    assert expected <= set(settings.INSTALLED_APPS)
