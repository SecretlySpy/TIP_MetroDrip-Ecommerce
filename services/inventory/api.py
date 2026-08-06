import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from contracts.errors import envelope
from contracts.inventory_v1 import (
    ROUTE_STOCK_BATCH,
    ROUTE_STOCK_ONE,
    StockBatchRequest,
    StockBatchResponse,
    StockRecordOut,
)
from services._shared.security import ServiceAuth

from .database import get_db
from .models import Reservation, ReservationStatus, StockRecord

auth = ServiceAuth("INVENTORY_SERVICE_TOKEN")

# Applied to the whole router, not just the mutating route. This is an internal
# API with no user-scoped authorization of its own (ADR-H-001), and stock levels
# are commercially sensitive — there is no route here that should answer an
# unauthenticated caller. `POST /reservations` in particular was published on a
# host port with no check at all.
router = APIRouter(dependencies=[Depends(auth)])


def _as_out(record: StockRecord) -> StockRecordOut:
    return StockRecordOut(
        variant_id=record.variant_id,
        qty_on_hand=record.qty_on_hand,
        qty_reserved=record.qty_reserved,
        low_stock_threshold=record.low_stock_threshold,
        available=record.available,
    )


@router.post(ROUTE_STOCK_BATCH, response_model=StockBatchResponse)
async def get_stock_batch(
    payload: StockBatchRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
):
    """Counters for many SKUs in one round trip.

    Without this, reading a product page under `INVENTORY_PROVIDER=service`
    meant one HTTP call per variant — roughly 36 sequential calls per page on
    the seeded catalog, each with its own timeout budget. A missing id is
    omitted from `records`; the client fills it in as zero availability, which
    matches how the in-process provider treats an unstocked variant.
    """
    wanted = list(dict.fromkeys(payload.variant_ids))
    if not wanted:
        return StockBatchResponse(records=[])

    result = await db.execute(select(StockRecord).where(StockRecord.variant_id.in_(wanted)))
    found = {record.variant_id: record for record in result.scalars().all()}
    return StockBatchResponse(records=[_as_out(found[vid]) for vid in wanted if vid in found])


@router.get(ROUTE_STOCK_ONE, response_model=StockRecordOut)
async def get_stock(variant_id: int, db: AsyncSession = Depends(get_db)):  # noqa: B008
    record = await db.get(StockRecord, variant_id)
    if not record:
        raise HTTPException(status_code=404, detail=envelope("unknown_variant", "No such SKU."))
    return _as_out(record)


@router.post("/reservations")
async def create_reservations(
    items: list[dict[str, int]],
    session_key: str = "",
    order_id: int | None = None,
    db: AsyncSession = Depends(get_db),  # noqa: B008
):
    """Reserve stock for multiple variants. Atomic."""
    created = []
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)

    # We lock rows in order of variant_id to avoid deadlocks.
    sorted_items = sorted(items, key=lambda x: x["variant_id"])

    try:
        for item in sorted_items:
            variant_id = item["variant_id"]
            qty = item["qty"]
            if qty <= 0:
                raise ValueError("Quantity must be positive")

            # Lock the StockRecord
            stmt = select(StockRecord).where(StockRecord.variant_id == variant_id).with_for_update()
            result = await db.execute(stmt)
            record = result.scalars().first()

            if not record:
                raise ValueError(f"Variant {variant_id} not found in inventory")

            if record.available < qty:
                raise ValueError(f"Insufficient stock for variant {variant_id}")

            record.qty_reserved += qty

            res = Reservation(
                variant_id=variant_id,
                qty=qty,
                session_key=session_key,
                order_id=order_id,
                expires_at=expires_at,
                status=ReservationStatus.ACTIVE.value,
            )
            db.add(res)
            created.append(res)

        await db.commit()
        return {"status": "success", "reservations": [r.id for r in created]}

    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
