"""Documented mobile error schema (H-1).

Every non-2xx response body is:

    {"error": {"code": "<machine-code>", "message": "<human text>",
               "fields": {"<field>": ["..."]}?}}

Clients switch on `code`, render `message`, and map `fields` onto form inputs.
"""

from rest_framework.views import exception_handler as drf_exception_handler

_STATUS_CODES = {
    400: "invalid_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "throttled",
    502: "provider_unavailable",
}


def error_payload(code, message, fields=None):
    from config.middleware import get_correlation_id

    body = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    # NFR-12: every error body carries the same id the response header echoes.
    cid = get_correlation_id()
    if cid:
        body["error"]["correlation_id"] = cid
    return body


def mobile_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        # Unhandled exceptions keep Django's 500 path (no detail leakage).
        return None

    data = response.data
    fields = None
    if isinstance(data, dict) and set(data) == {"detail"}:
        message = str(data["detail"])
    elif isinstance(data, dict):
        message = "Validation failed."
        fields = {
            key: [str(item) for item in value] if isinstance(value, list) else [str(value)]
            for key, value in data.items()
        }
    elif isinstance(data, list):
        message = "; ".join(str(item) for item in data) or "Request failed."
    else:
        message = str(data)

    code = _STATUS_CODES.get(response.status_code, "error")
    response.data = error_payload(code, message, fields)
    return response
