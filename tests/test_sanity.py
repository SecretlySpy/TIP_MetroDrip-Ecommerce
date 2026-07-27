"""A-1 smoke checks: the project must import and the DB config must honor
Hard Invariant 6 (MySQL backend, utf8mb4) before any feature work lands."""

from importlib import import_module

from django.conf import settings
from django.db import migrations


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


def test_catalog_migrations_enforce_mysql_defaults_for_fresh_and_existing_databases():
    """Both installation paths must retain an executable MySQL-invariant operation."""
    initial_migration = import_module("apps.catalog.migrations.0001_initial").Migration
    repair_migration = import_module(
        "apps.catalog.migrations.0002_enforce_mysql_defaults"
    ).Migration

    # The initial operation protects a brand-new schema before its first domain table.
    assert any(
        isinstance(operation, migrations.RunPython)
        and operation.code.__name__ == "configure_mysql_defaults"
        for operation in initial_migration.operations
    )
    # The forward repair reaches installations where the historical operation was skipped.
    assert any(
        isinstance(operation, migrations.RunPython)
        and operation.code.__name__ == "enforce_mysql_defaults"
        for operation in repair_migration.operations
    )
