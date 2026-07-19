"""Notification adapters (§8). Epic B needs only the low-stock email leg;
order/shipping email (FR-11) and Semaphore SMS (FR-12) arrive in Epics D/E
behind this same module boundary.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_low_stock_alert(records):
    """Email the low-stock SKU list to configured staff (FR-9); returns sent count.

    With no recipients configured the alert degrades to a log line — alerting
    is an enhancement around the scan, never a hard dependency, mirroring the
    handover's graceful-degradation rule for notification channels.
    """
    records = list(records)
    if not records:
        return 0

    recipients = settings.LOW_STOCK_ALERT_RECIPIENTS
    if not recipients:
        logger.info(
            "Low-stock scan flagged %d SKU(s); no alert recipients configured.", len(records)
        )
        return 0

    lines = [
        f"{record.variant.sku}: available {record.available} "
        f"(on hand {record.qty_on_hand}, reserved {record.qty_reserved}, "
        f"threshold {record.low_stock_threshold})"
        for record in records
    ]
    send_mail(
        subject=f"[MetroDrip] Low stock: {len(records)} SKU(s) at or below threshold",
        message="The following SKUs need restocking:\n\n" + "\n".join(lines),
        from_email=None,  # DEFAULT_FROM_EMAIL
        recipient_list=recipients,
    )
    return len(records)
