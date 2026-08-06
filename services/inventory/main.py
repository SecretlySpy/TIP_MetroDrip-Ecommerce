"""FastAPI entry point for the stock ledger.

Every mutation arrives over authenticated, idempotent, versioned REST (see
`api.py`). There is deliberately no asynchronous ingress.

A Redis pub/sub listener used to run here and commit reservations straight from
`inventory_events` messages. It was removed (ADR-P3-024): nothing published to
that channel any more once the Django provider moved to sync REST, and what
remained was a second write path into the ledger with **no authentication and
no idempotency guard** — anything able to reach Redis could decrement stock.
That is exactly what ADR-P3-007 item 2 meant by "drop Redis as the commit
path", and it contradicted the exclusive-writer decision in ADR-P3-013.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from . import api, database
from .database import Base

logger = logging.getLogger("metrodrip.inventory")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("SKIP_CREATE_ALL"):
        # No longer swallowed. A service that cannot reach or create its own
        # schema has nothing to serve, and hiding that behind a green container
        # is how two schema authorities over the same table names went unnoticed.
        #
        # Django owns this DDL under ADR-P3-013, so deployments set
        # SKIP_CREATE_ALL and let migrations be the single authority.
        async with database.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    yield


app = FastAPI(title="MetroDrip Inventory Service", lifespan=lifespan)

app.include_router(api.router)


@app.get("/health")
async def health_check():
    """Legacy alias — prefer /healthz/live and /healthz/ready."""
    return {"status": "ok"}


@app.get("/healthz/live")
async def live():
    """Liveness: the process is running. Says nothing about its dependencies."""
    return {"status": "ok"}


@app.get("/healthz/ready")
async def ready(response: Response):
    """Readiness: this instance can authenticate a caller and reach its ledger.

    This previously returned 200 with `db: degraded` when the database was
    unreachable, and offered an `INVENTORY_READY_SKIP_DB` escape hatch that
    returned 200 without probing at all. Both made the Compose healthcheck and
    `scripts/smoke-services.sh` structurally incapable of failing — a readiness
    probe that cannot report "not ready" is not a probe.
    """
    if not api.auth.configured:
        response.status_code = 503
        return {"status": "unavailable", "auth": "unconfigured"}

    try:
        from sqlalchemy import text

        async with database.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness probe failed: inventory database is unreachable.")
        response.status_code = 503
        return {"status": "unavailable", "auth": "configured", "db": "down"}

    return {"status": "ok", "auth": "configured", "db": "up"}
