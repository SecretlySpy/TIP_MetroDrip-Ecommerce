"""Development settings — safe defaults so a fresh clone runs with zero secrets."""

from .base import *  # noqa: F403

DEBUG = True

# Fallback key is fine here: dev.py must never be used in production (prod.py
# hard-requires a real key from the environment instead).
SECRET_KEY = SECRET_KEY or "dev-only-insecure-key-do-not-deploy"  # noqa: F405

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Emails print to the runserver console until a real provider is wired in (FR-11).
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
