"""Bearer-token authentication for the strangler sidecars, closed by default.

Both ends of these seams used to fail *open* on an empty token. The Django
adapters omitted the Authorization header when their token was unset, and each
service skipped its check entirely when its own token was unset. Two
independent "be lenient when unconfigured" defaults composed into an internal
API with no authentication at all — published on a host port, and in the
inventory sidecar's case guarding a write endpoint.

Unconfigured now means *refusing* traffic rather than accepting all of it, and
the same flag feeds readiness so a sidecar that cannot authenticate is never
reported ready.

Why not raise at import instead: a crash-looping container hides its own reason
behind a restart counter, while an unready one that answers a documented 503
states the problem plainly and stays inspectable. The safety property that
matters — an unauthenticated sidecar never serves and never reports ready — is
the same either way.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import Header, HTTPException

logger = logging.getLogger("metrodrip.services.security")


def _envelope(code: str, message: str) -> dict[str, dict[str, str]]:
    """Build the ADR-H-001 error envelope so clients can switch on `code`."""
    return {"error": {"code": code, "message": message}}


class ServiceAuth:
    """A bearer-token gate bound to one environment variable.

    The token is read per call rather than cached at import so that a sidecar
    picks up a rotated secret on restart-free redeploys, and so tests can drive
    both the configured and unconfigured paths without reimporting the app.
    """

    def __init__(self, env_name: str) -> None:
        self.env_name = env_name

    @property
    def token(self) -> str:
        return os.environ.get(self.env_name, "").strip()

    @property
    def configured(self) -> bool:
        """Whether this sidecar can authenticate anything at all."""
        return bool(self.token)

    def __call__(self, authorization: str | None = Header(default=None)) -> None:
        """FastAPI dependency: authorize one request or raise."""
        expected_token = self.token
        if not expected_token:
            logger.error(
                "%s is unset; refusing the request. An unauthenticated sidecar "
                "must not serve traffic.",
                self.env_name,
            )
            raise HTTPException(
                status_code=503,
                detail=_envelope(
                    "auth_not_configured",
                    f"{self.env_name} is not set; this service refuses all requests.",
                ),
            )

        # compare_digest keeps the comparison time independent of how many
        # leading characters a guess got right; `!=` on a secret leaks that.
        expected_header = f"Bearer {expected_token}"
        if not authorization or not hmac.compare_digest(authorization, expected_header):
            raise HTTPException(
                status_code=401,
                detail=_envelope("unauthorized", "A valid service bearer token is required."),
            )
