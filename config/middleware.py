"""Cross-cutting HTTP middleware (correlation IDs — SI FR-05 / NFR-12).

Every inbound request gets a stable X-Correlation-ID. The same value is:
  * attached to `request.correlation_id`
  * echoed on every response as `X-Correlation-ID`
  * bound into the logging context so structured log lines carry it
  * available to error envelopes via `get_correlation_id()`

Clients may supply their own id (propagated end-to-end); otherwise we mint a
URL-safe token. One checkout is then greppable across BFF, mobile API, and
worker logs with a single string.
"""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar

CORRELATION_HEADER = "X-Correlation-ID"
# Keep inbound ids short and log-safe; reject anything that looks like injection.
_INBOUND_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,128}$")

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Current request's correlation id, or empty string outside a request."""
    return _correlation_id.get()


class CorrelationIdFilter(logging.Filter):
    """Inject `correlation_id` into every LogRecord for formatter use."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "-"
        return True


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        inbound = request.headers.get(CORRELATION_HEADER, "").strip()
        if inbound and _INBOUND_ID_RE.fullmatch(inbound):
            cid = inbound
        else:
            cid = uuid.uuid4().hex
        request.correlation_id = cid
        token = _correlation_id.set(cid)
        try:
            response = self.get_response(request)
        finally:
            _correlation_id.reset(token)
        response[CORRELATION_HEADER] = cid
        return response
