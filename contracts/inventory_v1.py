"""Inventory service v1 — the stock ledger contract (ADR-P3-003 step 3).

Two rules shape every message here, and both come from mistakes already made
in this repo:

1. **Only scalars cross the boundary.** No ORM instances, no order objects.
   The previous adapter passed a Django `Order` to the service and then wrote
   the returned reservation id back into Django's own `Reservation` table
   (`service.py`), which only worked because both sides were secretly pointed
   at the same schema. Identity crossing the seam is a `checkout_id` minted by
   the caller before any write — never an order id, which does not exist yet.

2. **Every mutation carries an idempotency key.** Under sync REST a read
   timeout is indistinguishable from success unless the server can recognise a
   replay. `ServiceUncertain` from `apps/core/http.py` is precisely this case,
   and without a key the only safe response to it is to give up.

Money never appears in these messages. Quantities only.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

ROUTE_STOCK_BATCH = "/v1/stock/batch"
ROUTE_STOCK_ONE = "/v1/stock/{variant_id}"
ROUTE_STOCK_LOW = "/v1/stock/low"
ROUTE_ADJUSTMENTS = "/v1/stock/adjustments"
ROUTE_RESERVATIONS = "/v1/reservations"
ROUTE_COMMIT = "/v1/reservations/{checkout_id}/commit"
ROUTE_RELEASE = "/v1/reservations/{checkout_id}/release"
ROUTE_SWEEP = "/v1/maintenance/expire-reservations"


# --- Reads ------------------------------------------------------------------


class StockRecordOut(BaseModel):
    """One SKU's counters. `available` is derived server-side, never by clients."""

    variant_id: int
    qty_on_hand: int = 0
    qty_reserved: int = 0
    low_stock_threshold: int = 0
    available: int = 0


class StockBatchRequest(BaseModel):
    """Read many SKUs in one call. A product page needs every variant it lists."""

    variant_ids: list[int] = Field(default_factory=list)


class StockBatchResponse(BaseModel):
    records: list[StockRecordOut] = Field(default_factory=list)


class LowStockItem(BaseModel):
    """A SKU at or below threshold, with enough identity to alert on.

    `sku` is carried in the payload rather than looked up by the caller because
    catalog and inventory are the *same* target service (ADR-P3-003), so the
    join stays local. The email/SMS alert renders SKUs, not integers.
    """

    variant_id: int
    sku: str = ""
    product_name: str = ""
    available: int = 0
    low_stock_threshold: int = 0


class LowStockResponse(BaseModel):
    items: list[LowStockItem] = Field(default_factory=list)


# --- Reservation lifecycle --------------------------------------------------


class ReserveLine(BaseModel):
    variant_id: int
    qty: int = Field(ge=1)


class ReserveRequest(BaseModel):
    """Reserve every line atomically, or reserve nothing.

    All-or-nothing matters: a partially reserved cart would leave the caller
    holding stock for an order it is about to abandon.
    """

    checkout_id: str = Field(min_length=8, max_length=64)
    lines: list[ReserveLine] = Field(min_length=1)
    session_key: str = ""
    ttl_minutes: int | None = None


class ReservationOut(BaseModel):
    id: int
    variant_id: int
    qty: int


class ReserveResponse(BaseModel):
    checkout_id: str
    reservations: list[ReservationOut] = Field(default_factory=list)
    expires_at: str


class CommitRequest(BaseModel):
    """Turn a hold into a sale. `order_no` is a label for the audit row only."""

    order_no: str = ""


class ReleaseResponse(BaseModel):
    """Release is a safe no-op on an unknown checkout_id.

    Compensation runs on paths where the caller cannot know whether a reserve
    ever landed, so "nothing to release" must be success, not 404.
    """

    checkout_id: str
    released: int = 0


class CommitResponse(BaseModel):
    checkout_id: str
    committed: int = 0
    #: Per-variant totals actually committed. The caller reconciles against its
    #: own order lines with this, so it never has to read the ledger's rows.
    lines: list[ReservationOut] = Field(default_factory=list)


# --- Adjustments and maintenance -------------------------------------------


class AdjustRequest(BaseModel):
    """A non-sale physical stock change. Sales only ever come from commit."""

    variant_id: int
    delta: int
    reason: str
    ref_order_no: str = ""


class AdjustResponse(BaseModel):
    variant_id: int
    qty_on_hand: int
    qty_reserved: int
    available: int


class SweepResponse(BaseModel):
    expired: int = 0
