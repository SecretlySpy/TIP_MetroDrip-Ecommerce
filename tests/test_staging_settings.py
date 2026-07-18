"""Fail-fast contracts for the environment-driven staging configuration."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Each import runs in a clean child process because Django settings modules are
# intentionally import-once singletons. Real-looking but disposable values also
# ensure these tests never depend on the developer's untracked .env contents.
VALID_STAGING_ENVIRONMENT = {
    "DJANGO_SECRET_KEY": "test-only-" + ("s" * 64),
    "DJANGO_ALLOWED_HOSTS": "staging.example.test, health.example.test",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://staging.example.test",
    "STAGING_HOST": "staging.example.test",
    "MYSQL_DATABASE": "metrodrip_staging_test",
    "MYSQL_USER": "metrodrip_staging_test",
    "MYSQL_PASSWORD": "test-only-database-password",
    "MYSQL_HOST": "db",
    "MYSQL_PORT": "3306",
    "STAGING_SEED_PREVIEW_ENABLED": "1",
    "STAGING_ALLOW_INSECURE_HTTP": "0",
}


def _import_staging_settings(environment_overrides=None):
    """Import staging settings in isolation and return the child process result."""
    environment = os.environ.copy()
    environment.update(VALID_STAGING_ENVIRONMENT)
    environment.update(environment_overrides or {})

    # Printing a narrow JSON contract avoids exposing secrets while proving that
    # parsing, trimming, database reassignment, and security defaults all ran.
    command = [
        sys.executable,
        "-c",
        (
            "import json; import config.settings.staging as s; "
            "print(json.dumps({"
            "'allowed_hosts': s.ALLOWED_HOSTS, "
            "'csrf_origins': s.CSRF_TRUSTED_ORIGINS, "
            "'database': s.DATABASES['default']['NAME'], "
            "'port': s.DATABASES['default']['PORT'], "
            "'staging_host': s.STAGING_HOST, "
            "'preview': s.STAGING_SEED_PREVIEW_ENABLED, "
            "'ssl_redirect': s.SECURE_SSL_REDIRECT, "
            "'session_secure': s.SESSION_COOKIE_SECURE, "
            "'csrf_secure': s.CSRF_COOKIE_SECURE, "
            "'hsts_seconds': s.SECURE_HSTS_SECONDS, "
            "'silenced_checks': s.SILENCED_SYSTEM_CHECKS, "
            "'whitenoise': 'whitenoise.middleware.WhiteNoiseMiddleware' in s.MIDDLEWARE, "
            "'static_backend': s.STORAGES['staticfiles']['BACKEND']"
            "}))"
        ),
    ]
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_staging_settings_parse_valid_environment_and_keep_https_enabled():
    """A complete deployment environment should import with secure defaults."""
    result = _import_staging_settings()

    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed == {
        "allowed_hosts": ["staging.example.test", "health.example.test"],
        "csrf_origins": ["https://staging.example.test"],
        "database": "metrodrip_staging_test",
        "port": "3306",
        "staging_host": "staging.example.test",
        "preview": True,
        "ssl_redirect": True,
        "session_secure": True,
        "csrf_secure": True,
        "hsts_seconds": 2_592_000,
        "silenced_checks": ["security.W021"],
        "whitenoise": True,
        "static_backend": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    }


@pytest.mark.parametrize(
    "required_name",
    [
        "DJANGO_SECRET_KEY",
        "DJANGO_ALLOWED_HOSTS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "MYSQL_DATABASE",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_HOST",
        "MYSQL_PORT",
        "STAGING_HOST",
    ],
)
def test_staging_settings_reject_missing_required_values(required_name):
    """Whitespace must not let a required deployment value pass validation."""
    result = _import_staging_settings({required_name: "   "})

    assert result.returncode != 0
    assert f"Required environment variable {required_name} is missing." in result.stderr


@pytest.mark.parametrize("csv_name", ["DJANGO_ALLOWED_HOSTS", "DJANGO_CSRF_TRUSTED_ORIGINS"])
def test_staging_settings_reject_csv_values_without_entries(csv_name):
    """Separators alone must not produce an empty security allowlist."""
    result = _import_staging_settings({csv_name: " , , "})

    assert result.returncode != 0
    assert f"Required environment variable {csv_name} has no values." in result.stderr


@pytest.mark.parametrize(
    "invalid_host",
    [
        "*",
        "*.example.test",
        "https://staging.example.test",
        "staging.example.test:443",
        "staging.example.test/path",
        "single-label",
        "203.0.113.10",
        "staging_example.test",
    ],
)
def test_staging_settings_reject_non_literal_staging_hosts(invalid_host):
    """The proxy site key must be a literal local or public DNS hostname."""
    result = _import_staging_settings({"STAGING_HOST": invalid_host})

    assert result.returncode != 0
    assert "STAGING_HOST is not a valid deployment hostname." in result.stderr


@pytest.mark.parametrize(
    "invalid_hosts",
    ["*", "staging.example.test,*", ".example.test", "https://staging.example.test"],
)
def test_staging_settings_reject_wildcard_or_url_allowed_hosts(invalid_hosts):
    """Django's host allowlist must not accept catch-all or URL-shaped values."""
    result = _import_staging_settings({"DJANGO_ALLOWED_HOSTS": invalid_hosts})

    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS contains an invalid hostname." in result.stderr


@pytest.mark.parametrize(
    "weak_secret",
    [
        "short",
        "a" * 64,
        "django-insecure-" + ("abc123" * 10),
        "replace-with-a-unique-random-django-secret",
    ],
)
def test_staging_settings_reject_weak_or_placeholder_django_secrets(weak_secret):
    """A documented placeholder or trivially weak key must stop startup."""
    result = _import_staging_settings({"DJANGO_SECRET_KEY": weak_secret})

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY is too weak or is a placeholder." in result.stderr


@pytest.mark.parametrize(
    "weak_password",
    ["short", "a" * 32, "replace-with-a-random-app-password"],
)
def test_staging_settings_reject_weak_or_placeholder_mysql_passwords(weak_password):
    """The application database credential must not accept example values."""
    result = _import_staging_settings({"MYSQL_PASSWORD": weak_password})

    assert result.returncode != 0
    assert "MYSQL_PASSWORD is too weak or is a placeholder." in result.stderr


@pytest.mark.parametrize(
    "invalid_origin",
    [
        "http://staging.example.test",
        "https://user@staging.example.test",
        "https://staging.example.test/path",
        "https://staging.example.test?query=1",
        "https://staging.example.test:invalid",
        "https://*",
        "https://staging.example.test:",
    ],
)
def test_staging_settings_reject_non_origin_or_non_https_csrf_values(invalid_origin):
    """CSRF trust entries must be complete HTTPS origins, not arbitrary URLs."""
    result = _import_staging_settings({"DJANGO_CSRF_TRUSTED_ORIGINS": invalid_origin})

    assert result.returncode != 0
    assert "DJANGO_CSRF_TRUSTED_ORIGINS contains an invalid HTTPS origin." in result.stderr


@pytest.mark.parametrize("invalid_port", ["0", "65536", "3.14", "１２３４"])
def test_staging_settings_reject_invalid_mysql_ports(invalid_port):
    """The database driver should never receive an invalid TCP port."""
    result = _import_staging_settings({"MYSQL_PORT": invalid_port})

    assert result.returncode != 0
    assert "MYSQL_PORT is not a valid port." in result.stderr


@pytest.mark.parametrize(
    "flag_name", ["STAGING_SEED_PREVIEW_ENABLED", "STAGING_ALLOW_INSECURE_HTTP"]
)
def test_staging_settings_reject_ambiguous_boolean_flags(flag_name):
    """Words such as 'false' must not accidentally become truthy flags."""
    result = _import_staging_settings({flag_name: "false"})

    assert result.returncode != 0
    assert f"{flag_name} must be exactly 0 or 1." in result.stderr


def test_staging_settings_require_proxy_host_in_allowed_hosts():
    """A proxy/Django host typo should fail before serving redirect errors."""
    result = _import_staging_settings({"DJANGO_ALLOWED_HOSTS": "other.example.test"})

    assert result.returncode != 0
    assert "STAGING_HOST must appear exactly in DJANGO_ALLOWED_HOSTS." in result.stderr


def test_staging_settings_require_proxy_host_in_csrf_origins():
    """The public host must have a corresponding trusted form origin."""
    result = _import_staging_settings({"DJANGO_CSRF_TRUSTED_ORIGINS": "https://other.example.test"})

    assert result.returncode != 0
    assert "STAGING_HOST must match a hostname in DJANGO_CSRF_TRUSTED_ORIGINS." in result.stderr


def test_staging_settings_reject_insecure_http_for_public_host():
    """The smoke-only HTTP escape hatch must never weaken a public deployment."""
    result = _import_staging_settings({"STAGING_ALLOW_INSECURE_HTTP": "1"})

    assert result.returncode != 0
    assert "STAGING_ALLOW_INSECURE_HTTP may only be enabled for localhost." in result.stderr


def test_staging_local_smoke_override_disables_https_redirect_only_explicitly():
    """The local HTTP escape hatch should be opt-in and deterministic."""
    result = _import_staging_settings(
        {
            "STAGING_HOST": "localhost",
            "DJANGO_ALLOWED_HOSTS": "localhost",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://localhost:18443",
            "STAGING_ALLOW_INSECURE_HTTP": "1",
        }
    )

    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["ssl_redirect"] is False
    assert parsed["session_secure"] is False
    assert parsed["csrf_secure"] is False
