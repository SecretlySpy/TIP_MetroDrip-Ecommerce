"""Fulfillment booking microservice (Phase 3 strangler — step 2).

Owns *courier booking I/O only*. The Django `Shipment` row, zones, and courier
webhook stay in the monolith so order state and M2 are untouched.

Default packing path remains in-process (`SHIPPING_PROVIDER=jnt|simulated`).
Opt-in via `SHIPPING_PROVIDER=http` + `SHIPPING_SERVICE_URL`. Booking failures
return False to Django so manual waybill entry remains the launch fallback.
"""

from __future__ import annotations

import logging
import os
import random

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("metrodrip.fulfillment")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

app = FastAPI(title="MetroDrip Fulfillment Service", version="v1")
SERVICE_TOKEN = os.environ.get("SHIPPING_SERVICE_TOKEN", "")


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


def _authorize(authorization: str | None) -> None:
    if not SERVICE_TOKEN:
        return
    if authorization != f"Bearer {SERVICE_TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/healthz/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz/ready")
def ready() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/shipments/book", response_model=BookShipmentResponse)
def book_shipment(
    payload: BookShipmentRequest,
    authorization: str | None = Header(default=None),
) -> BookShipmentResponse:
    _authorize(authorization)
    cid = payload.correlation_id or "-"
    # Real J&T credentials are enhancement-tier; without them we mint a
    # deterministic-format simulated waybill so packing still progresses.
    prefix = "JNT" if payload.courier.lower() in {"jnt", "j&t", ""} else payload.courier.upper()[:3]
    number = "".join(str(random.randint(0, 9)) for _ in range(12))
    waybill = f"{prefix}{number}"
    tracking = f"https://www.jtexpress.ph/trajectoryQuery?waybillNo={waybill}"
    logger.info(
        "cid=%s book order=%s courier=%s waybill=%s",
        cid,
        payload.order_no,
        payload.courier,
        waybill,
    )
    return BookShipmentResponse(
        waybill_no=waybill,
        tracking_url=tracking,
        status="booked",
        mode="simulated",
    )
