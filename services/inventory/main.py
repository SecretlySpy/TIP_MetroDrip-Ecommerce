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
        # Setup database tables if they don't exist
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Start Redis listener for Order events
    await start_redis_listener()

    yield

    # Shutdown Redis listener
    await stop_redis_listener()


app = FastAPI(title="MetroDrip Inventory Service", lifespan=lifespan)

app.include_router(api.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
