"""Connection wiring for the stock ledger.

Under ADR-P3-013 this service is the *exclusive writer* of a **shared** schema:
the three inventory tables live in Django's database, created and versioned by
Django migrations, and nothing else writes them once the service owns them.
Rollback is therefore an environment variable rather than a data migration,
which given ADR-P3-002's precedent (a previous extraction broke 19 tests and
had to be reverted) is the property that matters most.

The engine is rebindable because tests must be able to point it at Django's
*test* schema. That was previously happening by accident — `conftest.py` set
`MYSQL_DATABASE_INVENTORY=test_metrodrip` with no test using it, which made
every service-provider result a false green (ADR-P3-012). The same wiring is
correct once it is deliberate, declared, and actually exercised.
"""

import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

Base = declarative_base()


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def build_database_url(database: str | None = None) -> str:
    """Assemble the ledger's DSN, optionally overriding the schema name."""
    user = os.environ.get("MYSQL_USER", "metrodrip")
    password = os.environ.get("MYSQL_PASSWORD", "metrodrip")
    host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    port = os.environ.get("MYSQL_PORT", "3306")
    name = database or os.environ.get("MYSQL_DATABASE_INVENTORY", "metrodrip_inventory")
    return f"mysql+aiomysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


# `echo` defaults off. It was unconditionally True, which logged every statement
# — including stock mutations — in every environment.
engine = create_async_engine(build_database_url(), echo=_flag("SQL_ECHO"))
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def configure(
    *, database: str | None = None, echo: bool | None = None, pooled: bool = True
) -> None:
    """Rebind the engine to another schema, disposing the previous one.

    Only tests and process startup should call this. Disposing matters: a
    leaked pool holds open connections against a schema the test harness is
    about to drop, which surfaces later as an unrelated hang.

    `pooled=False` selects `NullPool`, which tests need rather than want.
    Starlette's `TestClient` runs each request on a fresh event loop, while a
    pooled aiomysql connection stays bound to the loop that opened it — so the
    second request in a test reuses a connection whose transport belongs to a
    loop that is already closed, and fails with "Event loop is closed" rather
    than anything resembling the actual problem. NullPool opens and closes per
    checkout, so every connection belongs to the loop currently running.
    """
    global engine, AsyncSessionLocal

    previous = engine
    options = {"echo": _flag("SQL_ECHO") if echo is None else echo}
    if pooled:
        # One uvicorn worker sharing MySQL's connection budget with Django.
        options["pool_pre_ping"] = True
    else:
        options["poolclass"] = NullPool
    engine = create_async_engine(build_database_url(database), **options)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    if previous is not None:
        await previous.dispose()


async def get_db():
    """FastAPI dependency. Reads the module globals so `configure` takes effect."""
    async with AsyncSessionLocal() as session:
        yield session
