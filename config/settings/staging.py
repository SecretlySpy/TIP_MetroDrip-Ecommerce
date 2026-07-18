"""Staging settings for the single-host Docker/Caddy deployment."""

import os
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .prod import *  # noqa: F403
from .prod import _required_hostname_environment


def _environment_flag(name, *, default=False):
    """Parse an explicit 0/1 environment flag without truthy-string mistakes."""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    if raw_value not in {"0", "1"}:
        raise ImproperlyConfigured(f"{name} must be exactly 0 or 1.")
    return raw_value == "1"


# The proxy hostname must agree with both Django security allowlists. Requiring
# this at import prevents a typo from producing redirect loops or rejected CSRF
# requests only after the host is already live.
STAGING_HOST = _required_hostname_environment("STAGING_HOST")
if STAGING_HOST not in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("STAGING_HOST must appear exactly in DJANGO_ALLOWED_HOSTS.")
if STAGING_HOST not in {urlsplit(origin).hostname for origin in CSRF_TRUSTED_ORIGINS}:  # noqa: F405
    raise ImproperlyConfigured("STAGING_HOST must match a hostname in DJANGO_CSRF_TRUSTED_ORIGINS.")

# Temporary read-only visibility for the M1 "seed browsable" gate. C-2 replaces
# this page with the real catalog, after which the flag and route can be removed.
STAGING_SEED_PREVIEW_ENABLED = _environment_flag("STAGING_SEED_PREVIEW_ENABLED")

# This escape hatch exists only for local container smoke tests. It cannot be
# activated for a public hostname even if an operator sets the flag by mistake.
STAGING_ALLOW_INSECURE_HTTP = _environment_flag("STAGING_ALLOW_INSECURE_HTTP")
if STAGING_ALLOW_INSECURE_HTTP:
    if STAGING_HOST not in {"localhost", "127.0.0.1"}:
        raise ImproperlyConfigured("STAGING_ALLOW_INSECURE_HTTP may only be enabled for localhost.")
    SECURE_SSL_REDIRECT = False  # noqa: F405
    SESSION_COOKIE_SECURE = False  # noqa: F405
    CSRF_COOKIE_SECURE = False  # noqa: F405

# HSTS preload is intentionally deferred until the public domain has completed
# its launch bake-in. Silence only that known warning so CI can fail on every
# other deployment warning at WARNING level.
SILENCED_SYSTEM_CHECKS = ["security.W021"]
