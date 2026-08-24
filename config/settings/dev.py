"""Development settings — safe defaults so a fresh clone runs with zero secrets."""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = True

# Fallback key is fine here: dev.py must never be used in production (prod.py
# hard-requires a real key from the environment instead).
SECRET_KEY = SECRET_KEY or "dev-only-insecure-key-do-not-deploy"  # noqa: F405

# 10.0.2.2 is the Android emulator's alias for the host loopback, so every
# request from the app arrives with that Host header — without it here the API
# answers 400 for the emulator and only the emulator, which is a confusing way
# to lose an afternoon. Private LAN ranges cover physical devices on the same
# Wi-Fi. Development only: prod.py builds ALLOWED_HOSTS from the environment
# and rejects wildcards outright.
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "10.0.2.2",  # Android emulator -> host
    ".ngrok-free.app",
]
if DEBUG:
    import socket

    try:
        # Add this machine's LAN addresses so a phone on the same network can
        # reach the dev server by IP.
        ALLOWED_HOSTS += [
            address[4][0]
            for address in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        ]
    except OSError:
        pass

# Emails print to the runserver console until a real provider is wired in (FR-11).
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# An explicit provider always wins. When no provider is selected, retain the
# convenient development default: use PayMongo when a sandbox key is present,
# otherwise use the in-process simulator. Validate this at settings import so a
# typo or a keyless explicit PayMongo selection cannot fail later at checkout.
_configured_payment_provider = os.environ.get("PAYMENT_PROVIDER", "").strip()
_allowed_payment_providers = {"paymongo", "simulated"}
if _configured_payment_provider not in _allowed_payment_providers | {""}:
    raise ImproperlyConfigured(
        "PAYMENT_PROVIDER="
        f"{_configured_payment_provider} is not recognized; expected one of "
        f"{sorted(_allowed_payment_providers)}."
    )

PAYMONGO_SECRET_KEY = PAYMONGO_SECRET_KEY.strip()  # noqa: F405
_paymongo_secret = PAYMONGO_SECRET_KEY
_has_paymongo_secret = bool(_paymongo_secret)
if _configured_payment_provider == "paymongo" and not _has_paymongo_secret:
    raise ImproperlyConfigured(
        "PAYMENT_PROVIDER=paymongo requires PAYMONGO_SECRET_KEY in development."
    )

PAYMENT_PROVIDER = _configured_payment_provider or (  # noqa: F405
    "paymongo" if _has_paymongo_secret else "simulated"
)
if PAYMENT_PROVIDER == "paymongo" and not _paymongo_secret.startswith("sk_test_"):
    raise ImproperlyConfigured(
        "Development PayMongo checkout requires a sandbox PAYMONGO_SECRET_KEY "
        "starting with sk_test_; live and malformed keys are rejected."
    )
SHIPPING_PROVIDER = "simulated"
NOTIFICATION_PROVIDER = "console"
