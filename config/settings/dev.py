"""Development settings — safe defaults so a fresh clone runs with zero secrets."""

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

# Without PayMongo sandbox keys the demo checkout uses the simulated provider;
# with keys configured, dev uses the real sandbox end-to-end.
PAYMENT_PROVIDER = "paymongo" if PAYMONGO_SECRET_KEY else "simulated"  # noqa: F405
SHIPPING_PROVIDER = "simulated"
NOTIFICATION_PROVIDER = "console"
