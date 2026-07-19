"""In-process APScheduler wiring (§2: v1 background jobs; Celery only if needed).

Exactly ONE process may run these jobs (ADR-A-014 scaling consequence): the
reservation sweep is idempotent but duplicate schedulers would waste locks, and
duplicate low-stock scans would duplicate alert emails. The `run_scheduler`
management command is that single process.
"""

import logging
import zoneinfo

from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)


def sweep_expired_reservations():
    """B-2: return abandoned checkout holds to availability every minute."""
    # Long-lived job processes must recycle stale MySQL connections themselves;
    # there is no request/response cycle here to do it for them.
    close_old_connections()
    try:
        from apps.inventory.services import release_expired_reservations

        expired = release_expired_reservations()
        if expired:
            logger.info("Reservation sweep expired %d hold(s).", expired)
    finally:
        close_old_connections()


def run_low_stock_scan():
    """B-4: flag SKUs at/below threshold and send the staff alert email."""
    close_old_connections()
    try:
        from apps.inventory.services import scan_low_stock
        from apps.notifications.services import send_low_stock_alert

        flagged = send_low_stock_alert(scan_low_stock())
        if flagged:
            logger.info("Low-stock scan alerted on %d SKU(s).", flagged)
    finally:
        close_old_connections()


def build_scheduler(scheduler_class=BackgroundScheduler):
    """Assemble the configured scheduler without starting it (testable seam)."""
    scheduler = scheduler_class(timezone=zoneinfo.ZoneInfo(settings.TIME_ZONE))
    # coalesce + max_instances=1: if the process stalls, run each late job once,
    # never in overlapping bursts that would contend on the same row locks.
    scheduler.add_job(
        sweep_expired_reservations,
        "interval",
        seconds=settings.RESERVATION_SWEEP_INTERVAL_SECONDS,
        id="reservation-sweep",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_low_stock_scan,
        "interval",
        minutes=settings.LOW_STOCK_SCAN_INTERVAL_MINUTES,
        id="low-stock-scan",
        coalesce=True,
        max_instances=1,
    )
    return scheduler
