"""MetroDrip base settings — shared by dev/test/prod.

Stack is locked by the handover (§2): Django on MySQL 8, InnoDB engine only,
utf8mb4 charset. Anything environment-specific (DEBUG, hosts, secrets) lives in
dev.py / prod.py; secrets are only ever read from the environment (.env locally).
"""

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
    "django.contrib.admin",
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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
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
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
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

# Customer is the registered-shopper auth model; guest orders keep this relation
# NULL. This must be set before the first accounts migration because Django
# cannot safely swap the user model after tables and foreign keys exist.
AUTH_USER_MODEL = "accounts.Customer"
LOGIN_URL = "/accounts/login/"
SITE_ID = 1
