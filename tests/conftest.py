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
