"""Replay protection for the ledger's mutating endpoints.

Under synchronous REST a read timeout is indistinguishable from success: the
request was sent, so the mutation may or may not have been applied. The caller
sees `ServiceUncertain` (`apps/core/http.py`) and, without a way to recognise a
replay, its only safe move is to give up and compensate — which turns every
network blip into a lost checkout.

The guarantee here comes from *ordering*, not from the table:

    BEGIN
      INSERT idempotency row (status_code = 0)   -- may collide on the PK
      <apply the stock mutation>
      UPDATE the row with the real status + body
    COMMIT

Because the key row and the mutation commit together, "key present with a
terminal status" is true exactly when the mutation was applied. A crash between
the two rolls both back, so a retry re-runs cleanly rather than finding a claim
with nothing behind it.

Three outcomes on collision, and they are genuinely different:

- fingerprint differs  → 422. Same key, different body: a client bug, never a
                         retry, and replaying the first response would be a lie.
- status_code == 0     → 409 with Retry-After. The original is still in flight;
                         answering now would either double-apply or guess.
- otherwise            → replay the stored status and body verbatim.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from contracts.errors import envelope

from .models import IdempotencyRecord

#: How long a claim may sit at status 0 before we assume the claimant died.
#: Longer than any single request's read timeout, shorter than the reservation
#: TTL — a stale claim must clear well before the stock it guards expires.
IN_FLIGHT_GRACE_SECONDS = 60


def hash_key(route: str, key: str) -> str:
    """Namespace the key by route so one id can guard reserve *and* commit."""
    return hashlib.sha256(f"{route}:{key}".encode()).hexdigest()


def fingerprint(payload) -> str:
    """Canonical hash of a request body, stable across key ordering."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class Replay(Exception):
    """Raised to short-circuit a handler with an already-computed response."""

    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self.body = body
        super().__init__(f"replaying {status_code}")


async def claim(db, *, route: str, key: str, payload) -> str:
    """Claim `key` for this request, or raise `Replay` / `HTTPException`.

    Returns the key hash, which the caller passes back to `record()` before
    committing. Must run inside the same transaction as the mutation.
    """
    if not key:
        raise HTTPException(
            status_code=400,
            detail=envelope(
                "idempotency_key_required",
                "This endpoint mutates stock; send an Idempotency-Key header.",
            ),
        )

    key_hash = hash_key(route, key)
    request_hash = fingerprint(payload)

    db.add(
        IdempotencyRecord(
            key_hash=key_hash,
            request_fingerprint=request_hash,
            status_code=0,
            response_body={},
        )
    )
    try:
        # Forces the INSERT now so the PK collision surfaces here rather than at
        # commit, when the mutation would already have been applied.
        await db.flush()
    except IntegrityError:
        await db.rollback()
        await _resolve_existing(db, key_hash=key_hash, request_hash=request_hash)

    return key_hash


async def _resolve_existing(db, *, key_hash: str, request_hash: str) -> None:
    result = await db.execute(
        select(IdempotencyRecord).where(IdempotencyRecord.key_hash == key_hash)
    )
    existing = result.scalars().first()
    if existing is None:
        # The claimant rolled back between our collision and this read, so the
        # key is free again. Ask the client to retry rather than racing it.
        raise HTTPException(
            status_code=409,
            detail=envelope("in_progress", "Retry this request."),
            headers={"Retry-After": "1"},
        )

    if existing.request_fingerprint != request_hash:
        raise HTTPException(
            status_code=422,
            detail=envelope(
                "idempotency_key_reuse",
                "This Idempotency-Key was used with a different request body.",
            ),
        )

    if existing.status_code == 0:
        raise HTTPException(
            status_code=409,
            detail=envelope("in_progress", "An identical request is still being processed."),
            headers={"Retry-After": "1"},
        )

    raise Replay(existing.status_code, existing.response_body or {})


async def record(db, *, key_hash: str, status_code: int, body: dict) -> None:
    """Store the outcome. Must be called before the caller commits."""
    result = await db.execute(
        select(IdempotencyRecord).where(IdempotencyRecord.key_hash == key_hash)
    )
    row = result.scalars().first()
    if row is not None:
        row.status_code = status_code
        row.response_body = body
