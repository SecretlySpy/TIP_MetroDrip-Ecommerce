"""Notifications delivery microservice (Phase 3 strangler — thinnest seam).

Owns *outbound delivery only* (email / SMS / Expo push HTTP). Inbox rows
(`Notification`, `DeviceToken`) and order FKs stay in the Django monolith so
the mobile notification centre and M2 stock path are untouched.

Default production path remains in-process (`NOTIFICATION_PROVIDER=console|
email_sms`). This service is opt-in via `NOTIFICATION_PROVIDER=http` and
`NOTIFICATION_SERVICE_URL`. Failures never raise into callers — the Django
HTTP adapter logs and returns False.

No message broker, no mesh, no K8s. Synchronous versioned REST only.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Any

import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("metrodrip.notifications")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

app = FastAPI(title="MetroDrip Notifications Service", version="v1")

SERVICE_TOKEN = os.environ.get("NOTIFICATION_SERVICE_TOKEN", "")
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class EmailPayload(BaseModel):
    to: list[str] = Field(min_length=1)
    subject: str
    body: str
    correlation_id: str | None = None


class SmsPayload(BaseModel):
    phone: str
    message: str
    correlation_id: str | None = None


class PushPayload(BaseModel):
    tokens: list[str] = Field(default_factory=list)
    title: str
    body: str
    data: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


def _authorize(authorization: str | None) -> None:
    """Default-deny when a service token is configured."""
    if not SERVICE_TOKEN:
        return
    expected = f"Bearer {SERVICE_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/healthz/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz/ready")
def ready() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/email")
def send_email(payload: EmailPayload, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    cid = payload.correlation_id or "-"
    host = os.environ.get("SMTP_HOST", "")
    if not host:
        logger.info("cid=%s email simulated to=%s subject=%s", cid, payload.to, payload.subject)
        return {"delivered": True, "mode": "simulated"}

    msg = EmailMessage()
    msg["Subject"] = payload.subject
    msg["From"] = os.environ.get("SMTP_FROM", "no-reply@metrodrip.local")
    msg["To"] = ", ".join(payload.to)
    msg.set_content(payload.body)
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if os.environ.get("SMTP_STARTTLS", "1") == "1":
                smtp.starttls()
            user = os.environ.get("SMTP_USER", "")
            if user:
                smtp.login(user, os.environ.get("SMTP_PASSWORD", ""))
            smtp.send_message(msg)
        return {"delivered": True, "mode": "smtp"}
    except Exception:
        logger.exception("cid=%s email delivery failed", cid)
        raise HTTPException(status_code=502, detail="email_failed") from None


@app.post("/v1/sms")
def send_sms(payload: SmsPayload, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    cid = payload.correlation_id or "-"
    api_key = os.environ.get("SEMAPHORE_API_KEY", "")
    if not api_key:
        logger.info("cid=%s sms simulated phone=%s", cid, payload.phone)
        return {"delivered": True, "mode": "simulated"}

    try:
        response = requests.post(
            "https://api.semaphore.co/api/v4/messages",
            data={
                "apikey": api_key,
                "number": payload.phone,
                "message": payload.message,
                "sendername": os.environ.get("SEMAPHORE_SENDER_NAME", "MetroDrip"),
            },
            timeout=10,
        )
        response.raise_for_status()
        return {"delivered": True, "mode": "semaphore"}
    except Exception:
        logger.exception("cid=%s sms delivery failed", cid)
        raise HTTPException(status_code=502, detail="sms_failed") from None


@app.post("/v1/push")
def send_push(payload: PushPayload, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    cid = payload.correlation_id or "-"
    tokens = [t for t in payload.tokens if t]
    if not tokens:
        return {"delivered": 0, "mode": "noop"}

    if os.environ.get("PUSH_PROVIDER", "simulated") != "expo":
        logger.info("cid=%s push simulated n=%d title=%s", cid, len(tokens), payload.title)
        return {"delivered": len(tokens), "mode": "simulated"}

    try:
        messages = [
            {
                "to": token,
                "title": payload.title,
                "body": payload.body,
                "data": payload.data,
                "sound": "default",
            }
            for token in tokens
        ]
        response = requests.post(EXPO_PUSH_URL, json=messages, timeout=10)
        response.raise_for_status()
        return {"delivered": len(tokens), "mode": "expo"}
    except Exception:
        logger.exception("cid=%s push delivery failed", cid)
        raise HTTPException(status_code=502, detail="push_failed") from None
