"""The stock ledger's HTTP surface (ADR-P3-003 step 3).

Every mutating route is authenticated, idempotent, and atomic. Reservations are
addressed by the caller's `checkout_id`, never by ids this service minted:
that is what lets a caller compensate for a request whose outcome it never
learned, and what removes any need for it to read these tables.
"""

import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from contracts.errors import envelope
from contracts.inventory_v1 import (
    ROUTE_ADJUSTMENTS,
    ROUTE_COMMIT,
    ROUTE_RELEASE,
    ROUTE_RESERVATIONS,
    ROUTE_STOCK_BATCH,
    ROUTE_STOCK_ONE,
    ROUTE_SWEEP,
    AdjustRequest,
    AdjustResponse,
    CommitRequest,
    CommitResponse,
    ReleaseResponse,
    ReservationOut,
    ReserveRequest,
    ReserveResponse,
    StockBatchRequest,
    StockBatchResponse,
    StockRecordOut,
    SweepResponse,
)
from services._shared.security import ServiceAuth

from . import idempotency
from .database import get_db
from .models import (
    IdempotencyRecord,  # noqa: F401 — imported so Base.metadata knows the table
    MovementReason,
    Reservation,
    ReservationStatus,
    StockMovement,
    StockRecord,
)

auth = ServiceAuth("INVENTORY_SERVICE_TOKEN")

# Applied to the whole router, not just the mutating routes. This is an internal
# API with no user-scoped authorization of its own (ADR-H-001), and stock levels
# are commercially sensitive — there is no route here that should answer an
# unauthenticated caller. `POST /reservations` in particular was published on a
# host port with no check at all.
router = APIRouter(dependencies=[Depends(auth)])

DEFAULT_TTL_MINUTES = 15


def _now():
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def _as_out(record: StockRecord) -> StockRecordOut:
    return StockRecordOut(
        variant_id=record.variant_id,
        qty_on_hand=record.qty_on_hand,
        qty_reserved=record.qty_reserved,
        low_stock_threshold=record.low_stock_threshold,
        available=record.available,
    )


# --- Reads ------------------------------------------------------------------


@router.post(ROUTE_STOCK_BATCH, response_model=StockBatchResponse)
async def get_stock_batch(
    payload: StockBatchRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
):
    """Counters for many SKUs in one round trip.

    Without this, reading a product page meant one HTTP call per variant —
    roughly 36 sequential calls on the seeded catalog, each with its own
    timeout budget. Missing ids are omitted; the client fills them in as zero,
    matching how the in-process provider treats an unstocked variant.
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


# --- Reservation lifecycle --------------------------------------------------


@router.post(ROUTE_RESERVATIONS, response_model=ReserveResponse)
async def create_reservations(
    payload: ReserveRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Reserve every line atomically under one `checkout_id`, or reserve nothing.

    Rows are locked in `variant_id` order. One global lock order means two carts
    sharing SKUs can block each other but can never form a cycle, which is what
    keeps the 20-buyers/10-units gate deterministic.
    """
    body = payload.model_dump()
    try:
        key_hash = await idempotency.claim(
            db, route=ROUTE_RESERVATIONS, key=idempotency_key or payload.checkout_id, payload=body
        )
    except idempotency.Replay as replay:
        response.status_code = replay.status_code
        response.headers["Idempotency-Replayed"] = "true"
        return replay.body

    ttl = payload.ttl_minutes or DEFAULT_TTL_MINUTES
    expires_at = _now() + datetime.timedelta(minutes=ttl)
    created = []

    for line in sorted(payload.lines, key=lambda item: item.variant_id):
        locked = await db.execute(
            select(StockRecord).where(StockRecord.variant_id == line.variant_id).with_for_update()
        )
        record = locked.scalars().first()
        if record is None:
            await db.rollback()
            raise HTTPException(
                status_code=404,
                detail=envelope(
                    "unknown_variant", f"Variant {line.variant_id} has no stock record."
                ),
            )
        if record.available < line.qty:
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail=envelope(
                    "insufficient_stock",
                    f"Variant {line.variant_id}: requested {line.qty}, "
                    f"available {record.available}.",
                ),
            )

        record.qty_reserved += line.qty
        reservation = Reservation(
            variant_id=line.variant_id,
            qty=line.qty,
            session_key=payload.session_key,
            checkout_id=payload.checkout_id,
            expires_at=expires_at,
            status=ReservationStatus.ACTIVE.value,
        )
        db.add(reservation)
        created.append(reservation)

    await db.flush()
    result = ReserveResponse(
        checkout_id=payload.checkout_id,
        reservations=[
            ReservationOut(id=row.id, variant_id=row.variant_id, qty=row.qty) for row in created
        ],
        expires_at=expires_at.isoformat(),
    )
    await idempotency.record(db, key_hash=key_hash, status_code=201, body=result.model_dump())
    await db.commit()
    response.status_code = 201
    return result


@router.post(ROUTE_COMMIT, response_model=CommitResponse)
async def commit_reservations(
    checkout_id: str,
    payload: CommitRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Turn a checkout group's ACTIVE holds into sales, with their audit rows.

    A group with nothing active commits zero rather than failing: the payment
    webhook is the only payment truth (Invariant 3) and providers retry it, so
    a replay must be a no-op, not an error.
    """
    body = payload.model_dump()
    try:
        key_hash = await idempotency.claim(
            db, route=ROUTE_COMMIT, key=idempotency_key or f"{checkout_id}:commit", payload=body
        )
    except idempotency.Replay as replay:
        response.headers["Idempotency-Replayed"] = "true"
        return replay.body

    locked = await db.execute(
        select(Reservation)
        .where(
            Reservation.checkout_id == checkout_id,
            Reservation.status == ReservationStatus.ACTIVE.value,
        )
        .order_by(Reservation.variant_id)
        .with_for_update()
    )
    reservations = list(locked.scalars().all())

    committed = []
    for reservation in reservations:
        stock_result = await db.execute(
            select(StockRecord)
            .where(StockRecord.variant_id == reservation.variant_id)
            .with_for_update()
        )
        record = stock_result.scalars().first()
        if record is None or record.qty_on_hand < reservation.qty:
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail=envelope(
                    "counters_cannot_cover_sale",
                    f"Variant {reservation.variant_id} cannot cover the committed sale.",
                ),
            )

        record.qty_on_hand -= reservation.qty
        record.qty_reserved -= reservation.qty
        db.add(
            StockMovement(
                variant_id=reservation.variant_id,
                delta=-reservation.qty,
                reason=MovementReason.SALE.value,
            )
        )
        reservation.status = ReservationStatus.COMMITTED.value
        reservation.ended_at = _now()
        committed.append(reservation)

    await db.flush()
    result = CommitResponse(
        checkout_id=checkout_id,
        committed=len(committed),
        lines=[
            ReservationOut(id=row.id, variant_id=row.variant_id, qty=row.qty) for row in committed
        ],
    )
    await idempotency.record(db, key_hash=key_hash, status_code=200, body=result.model_dump())
    await db.commit()
    return result


@router.post(ROUTE_RELEASE, response_model=ReleaseResponse)
async def release_reservations(
    checkout_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Return a checkout group's held units to availability.

    An unknown `checkout_id` releases zero and succeeds. Compensation runs
    exactly where the caller could not learn whether its reserve landed, so
    "nothing to release" has to be a success.
    """
    try:
        key_hash = await idempotency.claim(
            db, route=ROUTE_RELEASE, key=idempotency_key or f"{checkout_id}:release", payload={}
        )
    except idempotency.Replay as replay:
        response.headers["Idempotency-Replayed"] = "true"
        return replay.body

    locked = await db.execute(
        select(Reservation)
        .where(
            Reservation.checkout_id == checkout_id,
            Reservation.status == ReservationStatus.ACTIVE.value,
        )
        .order_by(Reservation.variant_id)
        .with_for_update()
    )
    reservations = list(locked.scalars().all())
    released = await _release_all(db, reservations, ReservationStatus.RELEASED)

    result = ReleaseResponse(checkout_id=checkout_id, released=released)
    await idempotency.record(db, key_hash=key_hash, status_code=200, body=result.model_dump())
    await db.commit()
    return result


async def _release_all(db, reservations, terminal_status) -> int:
    """Give each hold's units back, guarding against counter underflow."""
    released = 0
    for reservation in reservations:
        stock_result = await db.execute(
            select(StockRecord)
            .where(StockRecord.variant_id == reservation.variant_id)
            .with_for_update()
        )
        record = stock_result.scalars().first()
        if record is None or record.qty_reserved < reservation.qty:
            # Only reachable if something outside this service wrote the
            # counters. Fail loudly rather than storing a negative.
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail=envelope(
                    "reserved_underflow",
                    f"Variant {reservation.variant_id}: qty_reserved would go negative.",
                ),
            )
        record.qty_reserved -= reservation.qty
        reservation.status = terminal_status.value
        reservation.ended_at = _now()
        released += 1
    return released


# --- Adjustments and maintenance -------------------------------------------


@router.post(ROUTE_ADJUSTMENTS, response_model=AdjustResponse)
async def adjust_stock(
    payload: AdjustRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Apply a non-sale physical stock change with its audit row.

    Sales are never expressible here — they come only from committing a hold,
    so the ledger cannot record a sale that no one paid for.
    """
    body = payload.model_dump()
    try:
        key_hash = await idempotency.claim(
            db, route=ROUTE_ADJUSTMENTS, key=idempotency_key or "", payload=body
        )
    except idempotency.Replay as replay:
        response.headers["Idempotency-Replayed"] = "true"
        return replay.body

    if payload.delta == 0:
        raise HTTPException(
            status_code=400, detail=envelope("invalid_delta", "delta must be non-zero.")
        )
    if payload.reason == MovementReason.SALE.value:
        raise HTTPException(
            status_code=400,
            detail=envelope("invalid_reason", "Sales are recorded by committing a hold."),
        )
    if payload.reason not in {reason.value for reason in MovementReason}:
        raise HTTPException(
            status_code=400,
            detail=envelope("invalid_reason", f"Unknown reason {payload.reason!r}."),
        )
    if payload.reason in {MovementReason.RESTOCK.value, MovementReason.RETURN.value} and (
        payload.delta < 0
    ):
        raise HTTPException(
            status_code=400,
            detail=envelope("invalid_delta", f"{payload.reason} requires a positive delta."),
        )

    locked = await db.execute(
        select(StockRecord).where(StockRecord.variant_id == payload.variant_id).with_for_update()
    )
    record = locked.scalars().first()
    if record is None:
        raise HTTPException(status_code=404, detail=envelope("unknown_variant", "No such SKU."))

    new_on_hand = record.qty_on_hand + payload.delta
    if new_on_hand < record.qty_reserved:
        raise HTTPException(
            status_code=409,
            detail=envelope(
                "would_break_reserved_invariant",
                f"on-hand {new_on_hand} would drop below reserved {record.qty_reserved}.",
            ),
        )

    record.qty_on_hand = new_on_hand
    db.add(StockMovement(variant_id=payload.variant_id, delta=payload.delta, reason=payload.reason))
    await db.flush()

    result = AdjustResponse(
        variant_id=record.variant_id,
        qty_on_hand=record.qty_on_hand,
        qty_reserved=record.qty_reserved,
        available=record.available,
    )
    await idempotency.record(db, key_hash=key_hash, status_code=200, body=result.model_dump())
    await db.commit()
    return result


@router.post(ROUTE_SWEEP, response_model=SweepResponse)
async def expire_reservations(db: AsyncSession = Depends(get_db)):  # noqa: B008
    """TTL sweep: expire every overdue ACTIVE hold.

    Deliberately not idempotency-guarded — it is naturally idempotent (a hold
    can only leave ACTIVE once) and is driven by a scheduler, not a client.
    """
    locked = await db.execute(
        select(Reservation)
        .where(
            Reservation.status == ReservationStatus.ACTIVE.value,
            Reservation.expires_at <= _now(),
        )
        .order_by(Reservation.variant_id)
        .with_for_update()
    )
    expired = await _release_all(db, list(locked.scalars().all()), ReservationStatus.EXPIRED)
    await db.commit()
    return SweepResponse(expired=expired)


@router.get("/v1/stock/low")
async def scan_low_stock(db: AsyncSession = Depends(get_db)):  # noqa: B008
    """SKUs at or below threshold on *availability*, not shelf count.

    Catalog and inventory are the same target service (ADR-P3-003), so joining
    to the variant for its SKU stays a local query — which is why the low-stock
    alert can render SKUs rather than bare integers.
    """
    available = StockRecord.qty_on_hand - StockRecord.qty_reserved
    result = await db.execute(
        select(StockRecord)
        .where(available <= StockRecord.low_stock_threshold)
        .order_by(StockRecord.variant_id)
    )
    rows = result.scalars().all()
    return {
        "items": [
            {
                "variant_id": row.variant_id,
                "available": row.available,
                "low_stock_threshold": row.low_stock_threshold,
            }
            for row in rows
        ]
    }
