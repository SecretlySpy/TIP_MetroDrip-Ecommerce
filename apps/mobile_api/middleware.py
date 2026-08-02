"""NFR-22: every mobile request must carry its app version.

The header lets the server correlate behavior with released app versions and
enforce the /v1-for-life compatibility promise; requests without it are
malformed by contract and rejected before any view runs.
"""

from django.http import JsonResponse

from .errors import error_payload

MOBILE_API_PREFIX = "/api/mobile/"
VERSION_HEADER = "X-Client-Version"


class MobileClientVersionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(MOBILE_API_PREFIX) and not request.headers.get(VERSION_HEADER):
            return JsonResponse(
                error_payload(
                    "missing_client_version",
                    f"Send the app version in the {VERSION_HEADER} header.",
                ),
                status=400,
            )
        return self.get_response(request)
