"""Rate limiting for the back-office console logins (ADR-P3-029).

DRF's throttles cover `/api/mobile/v1/` only — they are applied per view class,
and the consoles are Django admin views that never pass through DRF. So the two
surfaces holding staff access to every order and customer record, `/admin/` and
`/merchant/`, had no brute-force control of any kind while the mobile API had a
10/min credential budget.

Two independent buckets, because they stop different attacks:

* **Per username** — one account guessed from many addresses. This is the
  load-bearing control: it is unaffected by proxies, botnets, or IPv6 address
  rotation, all of which defeat a per-IP limit.
* **Per client address** — many accounts probed from one address, which the
  per-username bucket cannot see because no single username accumulates
  failures.

The username bucket is deliberately the stricter of the two. Staff share office
networks and NAT, so a tight per-IP limit locks out colleagues of whoever
fat-fingered a password; a per-username limit only ever affects the account
actually under attack.

Counting failures rather than attempts is what keeps this from becoming a
self-inflicted outage: a successful login clears both buckets, so ordinary
typo-then-correct traffic never accumulates toward a lockout.
"""

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

#: Failures allowed per username before the account stops accepting logins.
DEFAULT_MAX_PER_USER = 5
#: Failures allowed per client address. Looser: staff share office NAT.
DEFAULT_MAX_PER_IP = 20
#: Fixed window, in seconds, that both counters and the lockout share.
DEFAULT_WINDOW_SECONDS = 15 * 60

_PREFIX = "console-login"


def _setting(name, default):
    return getattr(settings, name, default)


def client_address(request):
    """The address to attribute a failure to, honouring only trusted proxies.

    `X-Forwarded-For` is client-supplied and forgeable, so trusting it by
    default would hand an attacker an unlimited supply of fresh buckets — the
    per-IP limit would then be worse than none, because it would read as a
    control while enforcing nothing.

    `CONSOLE_LOGIN_TRUSTED_PROXY_DEPTH` names how many proxies of our own sit in
    front of Django (Caddy is one). Zero, the default, means read `REMOTE_ADDR`
    and ignore the header entirely. Above zero, count that many entries in from
    the *right*: each trusted proxy appends the address it actually saw, so the
    Nth-from-right entry is the earliest hop a client cannot forge.

    Returns an empty string when no address can be determined, which callers
    treat as "skip the per-IP bucket" rather than as a shared bucket that would
    lock every anonymous request out at once.
    """
    depth = int(_setting("CONSOLE_LOGIN_TRUSTED_PROXY_DEPTH", 0))
    if depth > 0:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if len(hops) >= depth:
            return hops[-depth]
        # Fewer hops than configured means the request did not traverse the
        # proxy chain we expect. Falling back to REMOTE_ADDR is the safe read:
        # it is whatever actually connected to us.
    return request.META.get("REMOTE_ADDR", "") or ""


def _key(bucket, value):
    """Namespaced cache key over a hash of the value.

    Usernames are email addresses. Hashing keeps personal data out of cache
    keys — which are readable by anyone with access to the cache, appear in
    Redis `SCAN` output, and outlive the request — and incidentally keeps every
    key a fixed, memcached-safe length.
    """
    digest = hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:32]
    return f"{_PREFIX}:{bucket}:{digest}"


def _count(key):
    return cache.get(key) or 0


def _increment(key, window):
    """Bump a fixed-window counter, creating it if absent.

    `cache.add` then `cache.incr` rather than get-then-set: the pair is atomic
    on every backend that supports it, so concurrent failed logins cannot both
    read 3 and both write 4. The window is set once by `add` and deliberately
    not extended by `incr`, so a lockout expires a fixed time after the *first*
    failure rather than sliding forward forever under a slow trickle of guesses.
    """
    if cache.add(key, 1, timeout=window):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        # The key expired between `add` and `incr`. Start a fresh window.
        cache.set(key, 1, timeout=window)
        return 1


def is_locked_out(*, username, request):
    """Whether this login should be refused before credentials are checked.

    Checked before authentication so a locked-out account costs an attacker a
    cache read instead of a password hash — the point of a lockout is to stop
    spending CPU on guesses, and verifying first would keep paying that cost.
    """
    window = int(_setting("CONSOLE_LOGIN_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS))
    if window <= 0:  # A non-positive window disables the control outright.
        return False

    max_user = int(_setting("CONSOLE_LOGIN_MAX_ATTEMPTS_PER_USER", DEFAULT_MAX_PER_USER))
    if username and _count(_key("user", username)) >= max_user:
        return True

    max_ip = int(_setting("CONSOLE_LOGIN_MAX_ATTEMPTS_PER_IP", DEFAULT_MAX_PER_IP))
    address = client_address(request) if request is not None else ""
    return bool(address) and _count(_key("ip", address)) >= max_ip


def record_failure(*, username, request):
    """Count one failed console login against both buckets."""
    window = int(_setting("CONSOLE_LOGIN_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS))
    if window <= 0:
        return

    if username:
        count = _increment(_key("user", username), window)
        max_user = int(_setting("CONSOLE_LOGIN_MAX_ATTEMPTS_PER_USER", DEFAULT_MAX_PER_USER))
        if count >= max_user:
            # The username is not logged: a failed login's "username" is
            # attacker-controlled input, and logging it verbatim writes
            # unvalidated data — and other people's passwords, typed one field
            # early — into a log that is retained and widely readable.
            logger.warning("Console login locked out an account after %d failures.", count)

    address = client_address(request) if request is not None else ""
    if address:
        _increment(_key("ip", address), window)


def clear(*, username, request):
    """Forget both buckets after a successful login."""
    if username:
        cache.delete(_key("user", username))
    address = client_address(request) if request is not None else ""
    if address:
        cache.delete(_key("ip", address))
