"""FastAPI entry point for the Inventory Microservice.

Handles stock reservations and stock queries.
Sync with orders is handled via Redis Pub/Sub in events.py.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from . import api, database
from .database import Base
from .events import start_redis_listener, stop_redis_listener

logger = logging.getLogger("metrodrip.inventory")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("SKIP_CREATE_ALL"):
        # No longer swallowed. A service that cannot reach or create its own
        # schema has nothing to serve, and hiding that behind a green container
        # is how two schema authorities over the same table names went unnoticed.
        async with database.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    if os.environ.get("INVENTORY_DISABLE_REDIS", "").strip() not in {"1", "true", "yes"}:
        try:
            await start_redis_listener()
        except Exception:
            # Redis is the (deprecated) async commit path, not a serving
            # dependency: readiness deliberately does not gate on it.
            logger.exception("Redis listener failed to start; continuing without it.")

    yield

    try:
        await stop_redis_listener()
    except Exception:
        logger.exception("Redis listener failed to stop cleanly.")


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
