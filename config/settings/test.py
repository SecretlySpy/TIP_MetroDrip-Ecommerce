"""Test settings — dev config with deterministic, fast test-only overrides.

Tests run against real MySQL (never SQLite): the zero-oversell release gate
depends on InnoDB row locks (SELECT ... FOR UPDATE), which other engines fake
or serialize, making the concurrency test meaningless.
"""

from .dev import *  # noqa: F403

# MD5 hashing makes user-creating tests fast; irrelevant to what's under test.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Captured in django.core.mail.outbox for assertions instead of printing.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Use DummyCache to prevent @cache_page from leaking state across tests.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}
