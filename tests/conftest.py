"""Shared pytest configuration.

This file used to start a session-scoped uvicorn subprocess running
`services.inventory.main:app` on port 8000, with
`MYSQL_DATABASE_INVENTORY=test_metrodrip`.

Both halves of that were wrong, and together they were worse than either:

1. `test_metrodrip` is pytest-django's *own* test database for `metrodrip`.
   The FastAPI service was therefore reading and writing
   `inventory_stockrecord` / `inventory_reservation` inside Django's schema —
   the same physical rows the ORM owns. Under Compose the same service points
   at `metrodrip_inventory`, a genuinely separate ledger, so the two modes had
   opposite semantics and the suite only ever exercised the forgiving one. It
   is also the only reason the dual-write in
   `apps/inventory/providers/service.py` appeared to work: the Django `UPDATE`
   found the row SQLAlchemy had just inserted because it was literally the same
   table.

2. Nothing consumed it. `INVENTORY_PROVIDER` defaults to `local` and no test
   overrides it, so the subprocess answered zero requests. It cost a process
   per run and bought the appearance of coverage.

Service-side behaviour is now tested in-process instead — see
`tests/contract/`, where a real Django provider is driven against a real
FastAPI app through the single egress point in `apps/core/http.py`. That needs
no subprocess, no port, and no second database, and it fails when the two sides
actually disagree.

Reintroducing a live sidecar for the Phase-B stock work will need a database
that is *not* Django's test database, created and torn down explicitly.
"""

import pytest


@pytest.fixture(autouse=True)
def _clear_content_type_cache():
    """Clear Django's ContentType object cache after every transaction=True test.

    When pytest-django's TransactionTestCase teardown runs, it flushes all
    tables (including django_content_type and auth_permission) and then
    re-seeds initial data via the post_migrate signal. However, Django caches
    ContentType objects in memory (ContentType._cache). If the next test's
    setup re-inserts content types, the stale cache contains PK references to
    rows that no longer exist (auto-increment was reset by TRUNCATE), causing
    duplicate-key IntegrityErrors on the fresh inserts.

    Clearing the cache here — after every test — ensures the first DB hit after
    a flush reads fresh rows and never conflicts with the re-seeded initial
    data. The cost is one SELECT per test that actually reads ContentTypes; the
    benefit is a deterministic suite that doesn't depend on run order.
    """
    yield
    # Only import if Django's app registry is ready (avoids import-time errors
    # when conftest is loaded before Django finishes initialising).
    try:
        from django.contrib.contenttypes.models import ContentType

        ContentType.objects.clear_cache()
    except Exception:  # noqa: BLE001
        pass
