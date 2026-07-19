"""Production settings — everything sensitive must come from the environment.

NFR-2: HTTPS everywhere, secure cookies, HSTS. Admin 2FA and rate limiting are
added in Epic F (F-2) per the strict build order.
"""

import ipaddress
import os
import re
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False

_HOST_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def _required_environment(name):
    """Return one non-empty deployment value or fail before Django starts."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"Required environment variable {name} is missing.")
    return value


def _required_csv_environment(name):
    """Parse a required comma-separated deployment setting."""
    values = [value.strip() for value in _required_environment(name).split(",")]
    populated_values = [value for value in values if value]
    if not populated_values:
        raise ImproperlyConfigured(f"Required environment variable {name} has no values.")
    return populated_values


def _normalize_deployment_hostname(hostname):
    """Return one canonical deployment hostname or reject unsafe host syntax."""
    normalized_hostname = hostname.casefold()
    if normalized_hostname in {"localhost", "127.0.0.1"}:
        return normalized_hostname

    # Public staging is certificate-backed DNS. Other IP literals, wildcard
    # patterns, URL syntax, and internal single-label names broaden trust or
    # cannot satisfy that contract, so they fail before Django starts.
    try:
        ipaddress.ip_address(normalized_hostname)
    except ValueError:
        pass
    else:
        raise ValueError("Only the local smoke-test IPv4 address is supported.")

    labels = normalized_hostname.split(".")
    if (
        len(normalized_hostname) > 253
        or len(labels) < 2
        or any(_HOST_LABEL_PATTERN.fullmatch(label) is None for label in labels)
        or not any("a" <= character <= "z" for character in labels[-1])
    ):
        raise ValueError("A deployment hostname must be a literal DNS name.")
    return normalized_hostname


def _required_hostnames_environment(name):
    """Parse a required host allowlist without accepting catch-all patterns."""
    try:
        return [
            _normalize_deployment_hostname(hostname) for hostname in _required_csv_environment(name)
        ]
    except ValueError as error:
        raise ImproperlyConfigured(
            f"Required environment variable {name} contains an invalid hostname."
        ) from error


def _required_hostname_environment(name):
    """Read one required literal deployment hostname."""
    try:
        return _normalize_deployment_hostname(_required_environment(name))
    except ValueError as error:
        raise ImproperlyConfigured(
            f"Required environment variable {name} is not a valid deployment hostname."
        ) from error


def _required_https_origins_environment(name):
    """Return origin-only HTTPS URLs suitable for Django's CSRF allowlist."""
    origins = _required_csv_environment(name)
    for origin in origins:
        try:
            parsed_origin = urlsplit(origin)
            port = parsed_origin.port
            normalized_hostname = _normalize_deployment_hostname(parsed_origin.hostname or "")
        except ValueError as error:
            raise ImproperlyConfigured(
                f"Required environment variable {name} contains an invalid HTTPS origin."
            ) from error

        expected_netloc = normalized_hostname if port is None else f"{normalized_hostname}:{port}"

        if (
            parsed_origin.scheme != "https"
            or not parsed_origin.hostname
            or parsed_origin.netloc.casefold() != expected_netloc
            or parsed_origin.username is not None
            or parsed_origin.password is not None
            or parsed_origin.path not in {"", "/"}
            or parsed_origin.query
            or parsed_origin.fragment
            or port == 0
        ):
            raise ImproperlyConfigured(
                f"Required environment variable {name} contains an invalid HTTPS origin."
            )
    return origins


def _required_port_environment(name):
    """Return a valid TCP port while preserving Django's expected string value."""
    value = _required_environment(name)
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 65_535:
        raise ImproperlyConfigured(f"Required environment variable {name} is not a valid port.")
    return value


def _required_secret_environment(name):
    """Reject weak or example Django keys before the deployment can boot."""
    value = _required_environment(name)
    normalized_value = value.casefold()
    if (
        len(value) < 50
        or len(set(value)) < 5
        or normalized_value.startswith("django-insecure-")
        or normalized_value.startswith("replace-with-")
    ):
        raise ImproperlyConfigured(
            f"Required environment variable {name} is too weak or is a placeholder."
        )
    return value


def _required_password_environment(name):
    """Reject short, low-diversity, or documented placeholder passwords."""
    value = _required_environment(name)
    if len(value) < 16 or len(set(value)) < 5 or value.casefold().startswith("replace-with-"):
        raise ImproperlyConfigured(
            f"Required environment variable {name} is too weak or is a placeholder."
        )
    return value


# Mock payment completion must never exist outside development (Invariant 3:
# webhooks are the only payment truth in any deployed environment).
if os.environ.get("MOCK_PAYMENTS", "").strip() == "1":
    raise ImproperlyConfigured("MOCK_PAYMENTS cannot be enabled in production or staging.")
MOCK_PAYMENTS = False

# Fail fast rather than silently using development credentials or hosts.
SECRET_KEY = _required_secret_environment("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = _required_hostnames_environment("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = _required_https_origins_environment("DJANGO_CSRF_TRUSTED_ORIGINS")

# base.py reads values while importing. Reassigning every deployment value from
# the validated result prevents whitespace or a malformed port from reaching the
# database driver and proves production never inherited development defaults.
DATABASES["default"].update(  # noqa: F405
    {
        "NAME": _required_environment("MYSQL_DATABASE"),
        "USER": _required_environment("MYSQL_USER"),
        "PASSWORD": _required_password_environment("MYSQL_PASSWORD"),
        "HOST": _required_environment("MYSQL_HOST"),
        "PORT": _required_port_environment("MYSQL_PORT"),
    }
)

# WhiteNoise middleware already sits after SecurityMiddleware in base.py; prod
# only upgrades the storage backend to hashed+compressed manifests. Product
# media remains reserved for object storage + CDN.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# --- Transport security (NFR-2) ---
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days; raise after launch bake-in
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Persistent DB connections for cheap-tier hosting (NFR-5).
DATABASES["default"]["CONN_MAX_AGE"] = 60  # noqa: F405

# Container platforms collect stdout/stderr. Keeping structured logger wiring in
# settings avoids untracked filesystem logs and lets the host rotate output.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
