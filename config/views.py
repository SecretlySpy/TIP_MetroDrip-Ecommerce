"""Operational HTTP probes used by container and reverse-proxy health checks."""

import logging

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
def liveness(request):
    """Report that the Django process can accept and route a request."""
    # Liveness deliberately avoids the database. Restarting a healthy process
    # cannot repair an external database outage and can create a restart loop.
    return JsonResponse({"status": "ok"})


@require_GET
def readiness(request):
    """Report whether the process can execute a minimal database query."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        # Do not expose credentials, topology, or driver text in the HTTP body.
        logger.warning("Database readiness probe failed.", exc_info=True)
        return JsonResponse({"status": "unavailable"}, status=503)

    return JsonResponse({"status": "ok"})
