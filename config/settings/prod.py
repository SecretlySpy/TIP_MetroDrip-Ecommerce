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


def _deployed_provider(name, *, allowed, default, forbidden=frozenset()):
    """Return an operator-chosen provider key, narrowed to what may deploy.

    Two rejections, for different reasons. A *forbidden* value is a real
    provider that is development-only — enabling it in a deployed environment
    would break a hard invariant. An *unrecognized* value is a typo, which
    would otherwise survive until a registry lookup raised somewhere far from
    the cause.

    This replaced a check-then-overwrite pair per provider, which read the
    environment only to reject one bad value and then assigned a hardcoded good
    one. The operator's choice was discarded, so the `http` strangler opt-ins
    (ADR-P3-003 steps 1 and 2) were unreachable in staging and production — the
    two consoles could ship a sidecar but never cut over to it.
    """
    value = os.environ.get(name, "").strip() or default
    if value in forbidden:
        raise ImproperlyConfigured(f"{name}={value} cannot be enabled in production or staging.")
    if value not in allowed:
        raise ImproperlyConfigured(
            f"{name}={value} is not a recognized provider; expected one of {sorted(allowed)}."
        )
    return value


def _require_strangler_token(provider_name, provider_value, token_name):
    """Refuse to boot an HTTP strangler provider that cannot authenticate.

    Both ends fail *open* on an empty token: the Django adapters omit the
    Authorization header, and the sidecars skip the check entirely. Those two
    defaults compose into an unauthenticated internal API, so an unset token has
    to mean "do not boot" rather than "no auth".
    """
    if provider_value == "http" and not os.environ.get(token_name, "").strip():
        raise ImproperlyConfigured(f"{provider_name}=http requires {token_name} to be set.")


# Mock payment completion must never exist outside development (Invariant 3:
# webhooks are the only payment truth in any deployed environment). Unlike the
# providers below this stays an unconditional assignment: there is genuinely one
# legal value in a deployed environment, so there is no operator choice to make.
if os.environ.get("PAYMENT_PROVIDER", "").strip() == "simulated":
    raise ImproperlyConfigured("Simulated payments cannot be enabled in production or staging.")
PAYMENT_PROVIDER = "paymongo"

SHIPPING_PROVIDER = _deployed_provider(
    "SHIPPING_PROVIDER",
    allowed={"jnt", "http"},
    default="jnt",
    forbidden={"simulated"},
)
_require_strangler_token("SHIPPING_PROVIDER", SHIPPING_PROVIDER, "SHIPPING_SERVICE_TOKEN")

NOTIFICATION_PROVIDER = _deployed_provider(
    "NOTIFICATION_PROVIDER",
    allowed={"email_sms", "http"},
    default="email_sms",
    forbidden={"console"},
)
_require_strangler_token(
    "NOTIFICATION_PROVIDER", NOTIFICATION_PROVIDER, "NOTIFICATION_SERVICE_TOKEN"
)

# `service` is withheld until the parity gate in ADR-P3-005 passes: it still
# stubs commits, adjustments, the TTL sweep, and the low-stock scan (ADR-P3-002),
# and it is the one sidecar a deployed environment could otherwise reach.
# Widening this set to {"local", "service"} is the cutover.
INVENTORY_PROVIDER = _deployed_provider(
    "INVENTORY_PROVIDER",
    allowed={"local"},
    default="local",
    forbidden={"service"},
)

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

# LOGGING is defined in base.py (correlation-id filter + cid=… format).
# Container platforms collect stdout/stderr; do not override here.
