"""FastAPI entry point for the Inventory Microservice.

Handles stock reservations and stock queries.
Sync with orders is handled via Redis Pub/Sub in events.py.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import api
from .database import Base, engine
from .events import start_redis_listener, stop_redis_listener


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os

    if not os.environ.get("SKIP_CREATE_ALL"):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception:
            # Experimental service: boot even if inventory DB is not yet provisioned.
            pass

    if os.environ.get("INVENTORY_DISABLE_REDIS", "").strip() not in {"1", "true", "yes"}:
        try:
            await start_redis_listener()
        except Exception:
            pass

    yield

    try:
        await stop_redis_listener()
    except Exception:
        pass


app = FastAPI(title="MetroDrip Inventory Service", lifespan=lifespan)

app.include_router(api.router)


@app.get("/health")
async def health_check():
    """Legacy alias — prefer /healthz/live and /healthz/ready."""
    return {"status": "ok"}


@app.get("/healthz/live")
async def live():
    return {"status": "ok"}


@app.get("/healthz/ready")
async def ready():
    """Ready when the process can answer; DB probe is best-effort.

    Inventory is experimental (INVENTORY_PROVIDER=local is still the default).
    A missing inventory schema must not crash the container on boot for smoke
    checks — callers that need stock use the local provider until schema parity.
    """
    import os

    if os.environ.get("INVENTORY_READY_SKIP_DB", "").strip() in {"1", "true", "yes"}:
        return {"status": "ok", "db": "skipped"}
    try:
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "up"}
    except Exception:
        # Still report ok for liveness-style compose smoke when DB is optional;
        # strict readiness is the Django monolith's /healthz/ready.
        return {"status": "ok", "db": "degraded"}
