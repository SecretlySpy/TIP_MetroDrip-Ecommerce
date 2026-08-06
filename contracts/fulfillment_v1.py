"""Fulfillment service v1 — courier booking DTOs.

Booking I/O only. The Django `Shipment` row, shipping zones, and the courier
webhook stay in the monolith (ADR-P3-005), so nothing here carries order state.
"""

from __future__ import annotations

from pydantic import BaseModel

ROUTE_BOOK = "/v1/shipments/book"


class BookShipmentRequest(BaseModel):
    order_no: str
    courier: str = "jnt"
    recipient_name: str = ""
    address_line1: str = ""
    city: str = ""
    phone: str = ""
    correlation_id: str | None = None


class BookShipmentResponse(BaseModel):
    waybill_no: str
    tracking_url: str
    status: str = "booked"
    mode: str = "simulated"
