"""Production settings — everything sensitive must come from the environment.

NFR-2: HTTPS everywhere, secure cookies, HSTS. Admin 2FA and rate limiting are
added in Epic F (F-2) per the strict build order.
"""

import os

from .base import *  # noqa: F403

DEBUG = False

# Fail fast at boot if the key is missing — a silent fallback here would be a
# security incident, not a convenience.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h]

# --- Transport security (NFR-2) ---
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days; raise after launch bake-in
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Persistent DB connections for cheap-tier hosting (NFR-5).
DATABASES["default"]["CONN_MAX_AGE"] = 60  # noqa: F405
