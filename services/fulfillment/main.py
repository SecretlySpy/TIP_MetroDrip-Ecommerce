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

from fastapi import Depends, FastAPI, Response
from pydantic import BaseModel

from services._shared.security import ServiceAuth

logger = logging.getLogger("metrodrip.fulfillment")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

app = FastAPI(title="MetroDrip Fulfillment Service", version="v1")
auth = ServiceAuth("SHIPPING_SERVICE_TOKEN")


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


@app.get("/healthz/live")
def live() -> dict[str, str]:
    """Liveness: the process is running. Says nothing about configuration."""
    return {"status": "ok"}


@app.get("/healthz/ready")
def ready(response: Response) -> dict[str, str]:
    """Readiness: this instance can actually serve an authenticated booking.

    A sidecar with no service token cannot authenticate anyone, so reporting it
    ready would put a container into rotation that answers 503 to every real
    request.
    """
    if not auth.configured:
        response.status_code = 503
        return {"status": "unavailable", "auth": "unconfigured"}
    return {"status": "ok", "auth": "configured"}


@app.post(
    "/v1/shipments/book",
    response_model=BookShipmentResponse,
    dependencies=[Depends(auth)],
)
def book_shipment(payload: BookShipmentRequest) -> BookShipmentResponse:
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
