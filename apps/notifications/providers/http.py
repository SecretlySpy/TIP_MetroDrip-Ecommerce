"""HTTP delivery adapter — opt-in strangler for the notifications service.

Selected with `NOTIFICATION_PROVIDER=http` and `NOTIFICATION_SERVICE_URL`.
Default remains `console` / `email_sms` (in-process). Failures are logged and
swallowed so checkout / order transitions never depend on the remote service
(enhancement-tier rule, same as push).
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from config.middleware import get_correlation_id

from . import NotificationProvider, register_provider

logger = logging.getLogger(__name__)


@register_provider("http")
class HttpNotificationProvider(NotificationProvider):
    """POST DTOs to services/notifications; never holds ORM models over the wire."""

    def _url(self, path: str) -> str:
        base = getattr(settings, "NOTIFICATION_SERVICE_URL", "").rstrip("/")
        return f"{base}{path}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        token = getattr(settings, "NOTIFICATION_SERVICE_TOKEN", "") or ""
        if token:
            headers["Authorization"] = f"Bearer {token}"
        cid = get_correlation_id()
        if cid:
            headers["X-Correlation-ID"] = cid
        return headers

    def _post(self, path: str, payload: dict) -> bool:
        url = self._url(path)
        if not url.startswith("http"):
            logger.error("NOTIFICATION_SERVICE_URL is not configured")
            return False
        payload = {**payload, "correlation_id": get_correlation_id() or None}
        try:
            response = requests.post(url, json=payload, headers=self._headers(), timeout=8)
            if response.status_code >= 400:
                logger.warning("notification service %s → %s", path, response.status_code)
                return False
            return True
        except Exception:
            logger.exception("notification service unreachable path=%s", path)
            return False

    def send_order_confirmation(self, order, status_url):
        email = (order.shipping_address or {}).get("email") or getattr(
            order.customer, "email", None
        )
        if not email:
            return False
        body = (
            f"Thanks for your order {order.order_no}.\n"
            f"Total: {order.total} centavos.\n"
            f"Track: {status_url}\n"
        )
        return self._post(
            "/v1/email",
            {
                "to": [email],
                "subject": f"MetroDrip order {order.order_no}",
                "body": body,
            },
        )

    def send_contact_alert(self, contact_message):
        recipients = list(getattr(settings, "CONTACT_ALERT_RECIPIENTS", None) or [])
        if not recipients:
            logger.info("contact alert skipped — no CONTACT_ALERT_RECIPIENTS")
            return False
        body = (
            f"From: {contact_message.name} <{contact_message.email}>\n\n{contact_message.message}"
        )
        return self._post(
            "/v1/email",
            {
                "to": recipients,
                "subject": f"[MetroDrip] Contact: {getattr(contact_message, 'subject', 'message')}",
                "body": body,
            },
        )

    def send_low_stock_alert(self, records):
        recipients = list(getattr(settings, "LOW_STOCK_ALERT_RECIPIENTS", None) or [])
        if not recipients or not records:
            return False
        lines = [
            f"- {getattr(r, 'variant_id', r)} available={getattr(r, 'available', '?')}"
            for r in records
        ]
        return self._post(
            "/v1/email",
            {
                "to": recipients,
                "subject": f"[MetroDrip] Low stock ({len(records)} SKUs)",
                "body": "Low stock:\n" + "\n".join(lines),
            },
        )

    def send_sms(self, phone_number, message):
        return self._post("/v1/sms", {"phone": phone_number, "message": message})
