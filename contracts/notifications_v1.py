"""Notifications service v1 — outbound delivery DTOs.

Delivery only. `Notification` and `DeviceToken` rows and the mobile inbox stay
in Django (ADR-P3-003), so these carry rendered content, never model state.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

ROUTE_EMAIL = "/v1/email"
ROUTE_SMS = "/v1/sms"
ROUTE_PUSH = "/v1/push"


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


class DeliveryResponse(BaseModel):
    """Email and SMS: one recipient set, delivered or not."""

    delivered: bool
    mode: str


class PushDeliveryResponse(BaseModel):
    """Push fans out, so it reports a count rather than a boolean."""

    delivered: int
    mode: str
