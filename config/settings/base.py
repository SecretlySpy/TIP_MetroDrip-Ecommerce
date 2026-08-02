"""MetroDrip base settings — shared by dev/test/prod.

Stack is locked by the handover (§2): Django on MySQL 8, InnoDB engine only,
utf8mb4 charset. Anything environment-specific (DEBUG, hosts, secrets) lives in
dev.py / prod.py; secrets are only ever read from the environment (.env locally).
"""

import datetime
import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv

# PyMySQL masquerades as MySQLdb so Django's "mysql" backend can use it.
# Chosen over mysqlclient because this is pure Python (no C build step on any
# platform); protocol-compatible, including SELECT ... FOR UPDATE. See DECISIONS.md.
pymysql.install_as_MySQLdb()

# BASE_DIR = repository root (manage.py lives here).
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Local development reads secrets from an untracked .env file; in CI/prod the
# variables come from the real environment and .env simply doesn't exist.
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")  # dev.py provides a fallback; prod.py requires it

DEBUG = False  # never default-on; dev.py opts in explicitly

ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    # Replaces "django.contrib.admin" so the admin uses MetroDrip branding.
    # AdminConfig still autodiscovers every app's admin.py exactly as before.
    "config.admin.MetroDripAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.flatpages",
    # MetroDrip apps (handover §8) — strict build order, one domain per app.
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
    # Public mobile API (Epic H / FR-21): DRF + JWT with refresh-token rotation.
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "apps.mobile_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # NFR-22: mobile requests must self-identify their app version.
    "apps.mobile_api.middleware.MobileClientVersionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Category menu in base.html. Lazily evaluated, so pages that
                # do not render the navigation issue no extra queries.
                "apps.catalog.context_processors.category_navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database (Hard Invariant 6: MySQL 8, InnoDB only, utf8mb4 from the first migration) ---
# MySQL 8 defaults to InnoDB + utf8mb4 already; the init_command pins the engine
# defensively so a misconfigured server can never silently create MyISAM tables.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("MYSQL_DATABASE", "metrodrip"),
        "USER": os.environ.get("MYSQL_USER", "metrodrip"),
        "PASSWORD": os.environ.get("MYSQL_PASSWORD", "metrodrip"),
        "HOST": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "PORT": os.environ.get("MYSQL_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET default_storage_engine=INNODB, sql_mode='STRICT_TRANS_TABLES'",
        },
        # pytest-created databases must also honor the charset invariant.
        "TEST": {
            "CHARSET": "utf8mb4",
            "COLLATION": "utf8mb4_0900_ai_ci",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- I18N / TZ: PH-only storefront, timestamps stored in UTC (USE_TZ) and
# rendered in Manila time.
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# collectstatic target; product images use object storage + CDN, never this disk (§2)
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Hard Invariant 2: every persisted amount is an integer count of Philippine
# centavos. Presentation code reads these constants instead of embedding symbols
# or decimal-place assumptions throughout templates and services.
CURRENCY_CODE = "PHP"
CURRENCY_SYMBOL = "₱"
CURRENCY_MINOR_UNITS = 2

# The temporary M1 seed browser must never leak into development/production by
# accident. Only staging.py can opt in through an explicit environment flag.
STAGING_SEED_PREVIEW_ENABLED = False

# --- Inventory reservations (FR-5) and low-stock alerts (FR-9) ---
# Checkout holds stock for 15 minutes; the sweep job releases abandoned holds so
# an abandoned cart restores availability within the M3 gate's 16-minute bound.
RESERVATION_TTL_MINUTES = 15
RESERVATION_SWEEP_INTERVAL_SECONDS = 60
LOW_STOCK_SCAN_INTERVAL_MINUTES = 60
# Empty recipient list disables the email leg of low-stock alerts without
# breaking the scan itself (the dashboard flag in FR-8/F epics reads the scan).
LOW_STOCK_ALERT_RECIPIENTS = [
    address.strip()
    for address in os.environ.get("LOW_STOCK_ALERT_RECIPIENTS", "").split(",")
    if address.strip()
]
DEFAULT_FROM_EMAIL = os.environ.get(
    "DJANGO_DEFAULT_FROM_EMAIL", "MetroDrip <no-reply@metrodrip.example>"
)

# --- Payments (D-2/D-3, Hard Invariant 3) ---
PAYMONGO_SECRET_KEY = os.environ.get("PAYMONGO_SECRET_KEY", "")
PAYMONGO_WEBHOOK_SECRET = os.environ.get("PAYMONGO_WEBHOOK_SECRET", "")
# Shared secret for the inbound courier webhook (§7). Unset = endpoint rejects
# everything, so a missing secret can never mean "accept anything".
COURIER_WEBHOOK_SECRET = os.environ.get("COURIER_WEBHOOK_SECRET", "")
# Sandbox-only simulated payment completion for demos without PayMongo keys.
# dev.py may enable it; prod.py refuses to boot with it on (fail closed).
# Payment provider registry key (simulated | paymongo)
PAYMENT_PROVIDER = "paymongo"
# Inventory provider registry key (local | service). "local" is the row-locked
# in-process implementation that upholds Hard Invariants 1 & 4; "service" opts
# into the experimental D-07 FastAPI client, which does not yet implement
# commits/adjustments/sweeps transactionally.
INVENTORY_PROVIDER = os.environ.get("INVENTORY_PROVIDER", "local")
# Shipping provider registry key (simulated | jnt)
SHIPPING_PROVIDER = "jnt"
# Notification provider registry key (console | email_sms)
NOTIFICATION_PROVIDER = "email_sms"

# --- Enhancement-tier APIs (§7 rule: never on the critical checkout path) ---
SEMAPHORE_API_KEY = os.environ.get("SEMAPHORE_API_KEY", "")
SEMAPHORE_SENDER_NAME = os.environ.get("SEMAPHORE_SENDER_NAME", "MetroDrip")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# FR-18: contact-form submissions are stored and emailed to staff; empty list
# degrades to store-only, mirroring the low-stock alert pattern.
CONTACT_ALERT_RECIPIENTS = [
    address.strip()
    for address in os.environ.get("CONTACT_ALERT_RECIPIENTS", "").split(",")
    if address.strip()
]

# Customer is the registered-shopper auth model; guest orders keep this relation
# NULL. This must be set before the first accounts migration because Django
# cannot safely swap the user model after tables and foreign keys exist.
AUTH_USER_MODEL = "accounts.Customer"
LOGIN_URL = "/accounts/login/"
SITE_ID = 1

# --- Public mobile API (Epic H: FR-21, NFR-18/NFR-22, D-12) ---
# Separate surface from internal service-to-service /api/v1/: this one is
# token-authenticated, throttled, versioned, and paginated at ≤ 20 items.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "120/min",
        # Credential endpoints get a much tighter budget (H-1 risk register).
        "auth-burst": "10/min",
    },
    "DEFAULT_PAGINATION_CLASS": "apps.mobile_api.pagination.MobilePageNumberPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.mobile_api.errors.mobile_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": datetime.timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": datetime.timedelta(days=30),
    # Rotation + blacklist: a stolen refresh token dies on first legitimate use,
    # and logout can revoke the pair (NFR-19 pairs with device secure storage).
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
}

# Deep-link scheme the app registers; payment redirects land back in the app.
MOBILE_APP_SCHEME = os.environ.get("MOBILE_APP_SCHEME", "metrodrip")
# Push provider registry key (simulated | expo) — simulated logs, never sends.
PUSH_PROVIDER = os.environ.get("PUSH_PROVIDER", "simulated")
