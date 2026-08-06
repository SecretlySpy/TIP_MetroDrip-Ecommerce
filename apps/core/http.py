"""The one place Django talks to an extracted service.

Every provider adapter posts through `call()` rather than reaching for
`requests` directly, so timeout policy, authentication, correlation-id
propagation, retry rules, and the circuit breaker are decided once.

The important thing this module buys is not retries — it is the *taxonomy*.
A caller must be able to tell these three apart, because the correct response
differs completely:

    ServiceRejected     4xx. The service understood and said no. Nothing
                        changed. Surface it to the user; never retry.
    ServiceUnavailable  The request provably never arrived (connect refused or
                        connect timeout). Nothing changed. Safe to retry
                        blind, or to compensate immediately.
    ServiceUncertain    A read timeout, or 5xx after the body was sent. The
                        request may or may not have been applied. Retrying
                        without an idempotency key can double-apply it.

`requests` collapses all of these into `RequestException`, which is why the
previous adapters could only ever do `except Exception: return False`. That is
survivable for notification delivery, where a lost message is enhancement-tier.
It is not survivable for stock reservation, where "maybe it was applied" is the
difference between under-selling and over-selling — which is why this lands in
Phase A, before any of that moves.

Splitting connect and read timeouts is what makes the distinction knowable: a
connect timeout is provably pre-send, a read timeout provably post-send.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass

import requests

from config.middleware import CORRELATION_HEADER, get_correlation_id

logger = logging.getLogger(__name__)


class ServiceCallError(Exception):
    """Base class for every failed call to an extracted service."""


class ServiceRejected(ServiceCallError):
    """The service answered 4xx. A business answer; no state changed."""

    def __init__(self, status_code: int, code: str = "", message: str = "", payload=None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.payload = payload if payload is not None else {}
        super().__init__(f"{status_code} {code or 'rejected'}: {message}".strip())


class ServiceUnavailable(ServiceCallError):
    """The request never reached the service. No state changed."""


class ServiceUncertain(ServiceCallError):
    """The request may have been applied. Retry only with an idempotency key."""


@dataclass(frozen=True)
class CallPolicy:
    """Per-call timeout, retry, and breaker settings.

    `attempts > 1` is only legal alongside an idempotency key — `call()`
    enforces that rather than trusting each caller to remember, because the
    failure it prevents (a silently double-applied reservation) is invisible in
    testing and expensive in production.
    """

    connect_timeout: float = 1.0
    read_timeout: float = 3.0
    attempts: int = 1
    backoff_base: float = 0.05
    retry_on: tuple[int, ...] = (502, 503, 504)
    breaker_key: str = ""
    breaker_threshold: int = 5
    breaker_cooldown: float = 30.0


class _CircuitBreaker:
    """Process-local consecutive-failure breaker.

    Deliberately not backed by the cache. `config/settings/test.py` uses
    `DummyCache` and no deployed environment runs a shared cache, so a
    cache-backed breaker would silently never trip in exactly the environments
    it exists to protect. Process-local means each worker learns independently,
    which at this scale (a handful of gunicorn workers) is fine.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def check(self, key: str, *, cooldown: float) -> None:
        if not key:
            return
        with self._lock:
            opened = self._opened_at.get(key)
            if opened is None:
                return
            if time.monotonic() - opened < cooldown:
                raise ServiceUnavailable(f"circuit open for {key}")
            # Cooldown elapsed: allow a single probe through (half-open).
            del self._opened_at[key]

    def record_success(self, key: str) -> None:
        if not key:
            return
        with self._lock:
            self._failures.pop(key, None)
            self._opened_at.pop(key, None)

    def record_failure(self, key: str, *, threshold: int) -> None:
        if not key:
            return
        with self._lock:
            count = self._failures.get(key, 0) + 1
            self._failures[key] = count
            if count >= threshold and key not in self._opened_at:
                self._opened_at[key] = time.monotonic()
                logger.error("circuit opened for %s after %d consecutive failures", key, count)

    def reset(self) -> None:
        """Test hook: forget all breaker state."""
        with self._lock:
            self._failures.clear()
            self._opened_at.clear()


BREAKER = _CircuitBreaker()


def _error_envelope(response: requests.Response) -> tuple[str, str, dict]:
    """Pull the ADR-H-001 `{"error": {code, message}}` shape out of a 4xx body."""
    try:
        payload = response.json()
    except ValueError:
        return "", response.text[:200], {}
    if isinstance(payload, dict):
        error = payload.get("error")
        # FastAPI's HTTPException nests the envelope under `detail`.
        if not isinstance(error, dict) and isinstance(payload.get("detail"), dict):
            error = payload["detail"].get("error")
        if isinstance(error, dict):
            return str(error.get("code", "")), str(error.get("message", "")), payload
    return "", str(payload)[:200], payload if isinstance(payload, dict) else {}


def call(
    method: str,
    url: str,
    *,
    policy: CallPolicy,
    json=None,
    params=None,
    service_token: str = "",
    token_setting_name: str = "",
    idempotency_key: str | None = None,
):
    """Perform one service call, or raise a member of the taxonomy above.

    Returns the decoded JSON body on success.
    """
    if policy.attempts > 1 and not idempotency_key:
        raise ValueError(
            "Retrying without an idempotency key can double-apply the request; "
            "pass idempotency_key or set attempts=1."
        )
    if not url.startswith("http"):
        raise ServiceUnavailable(f"service URL is not configured (got {url!r})")

    # Fail closed. Omitting the header when the token is unset — what both
    # adapters used to do — pairs with a service that skips its own check when
    # unconfigured, and the two compose into an unauthenticated internal API.
    if not service_token:
        raise ServiceUnavailable(
            f"{token_setting_name or 'service token'} is not set; refusing to call {url}"
        )

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {service_token}",
    }
    correlation_id = get_correlation_id()
    if correlation_id:
        headers[CORRELATION_HEADER] = correlation_id
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    last_error: ServiceCallError | None = None
    for attempt in range(1, policy.attempts + 1):
        BREAKER.check(policy.breaker_key, cooldown=policy.breaker_cooldown)
        try:
            response = requests.request(
                method.upper(),
                url,
                json=json,
                params=params,
                headers=headers,
                timeout=(policy.connect_timeout, policy.read_timeout),
            )
        except requests.exceptions.ReadTimeout as error:
            # The body was sent. The service may have applied it.
            BREAKER.record_failure(policy.breaker_key, threshold=policy.breaker_threshold)
            last_error = ServiceUncertain(f"read timeout calling {url}")
            last_error.__cause__ = error
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as error:
            # Never established a connection, so nothing was applied.
            BREAKER.record_failure(policy.breaker_key, threshold=policy.breaker_threshold)
            last_error = ServiceUnavailable(f"cannot reach {url}")
            last_error.__cause__ = error
        except requests.exceptions.RequestException as error:
            BREAKER.record_failure(policy.breaker_key, threshold=policy.breaker_threshold)
            last_error = ServiceUncertain(f"transport failure calling {url}")
            last_error.__cause__ = error
        else:
            if response.status_code < 400:
                BREAKER.record_success(policy.breaker_key)
                try:
                    return response.json()
                except ValueError:
                    return {}

            if 400 <= response.status_code < 500:
                # A considered answer, not a fault: the breaker stays closed.
                BREAKER.record_success(policy.breaker_key)
                code, message, payload = _error_envelope(response)
                raise ServiceRejected(response.status_code, code, message, payload)

            BREAKER.record_failure(policy.breaker_key, threshold=policy.breaker_threshold)
            last_error = ServiceUncertain(f"{url} returned {response.status_code}")
            if response.status_code not in policy.retry_on:
                break

        if attempt < policy.attempts:
            # Jitter so concurrent callers do not retry in lockstep.
            delay = policy.backoff_base * (2 ** (attempt - 1))
            time.sleep(delay * (0.5 + random.random()))

    logger.warning("service call failed url=%s attempts=%d: %s", url, policy.attempts, last_error)
    raise last_error
