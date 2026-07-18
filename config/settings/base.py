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
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
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

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# collectstatic target; product images use object storage + CDN, never this disk (§2)
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
