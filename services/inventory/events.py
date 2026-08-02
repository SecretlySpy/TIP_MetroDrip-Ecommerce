import asyncio
import json
import logging
import os

import redis.asyncio as redis
from sqlalchemy import func, select

from .database import AsyncSessionLocal
from .models import MovementReason, Reservation, ReservationStatus, StockMovement, StockRecord

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

redis_client = None
pubsub = None
listener_task = None


async def process_event(event_type: str, data: dict):
    logger.info(f"Received event: {event_type} - {data}")
    async with AsyncSessionLocal() as db:
        if event_type == "OrderConfirmed":
            # order_id, reservations
            # Commit reservations, deduct qty_on_hand
            res_ids = data.get("reservations", [])
            order_id = data.get("order_id")

            for res_id in res_ids:
                stmt = select(Reservation).where(Reservation.id == res_id).with_for_update()
                result = await db.execute(stmt)
                res = result.scalars().first()
                if res and res.status == ReservationStatus.ACTIVE:
                    res.status = ReservationStatus.COMMITTED.value
                    res.order_id = order_id
                    res.ended_at = func.now()

                    # Update stock
                    stmt2 = (
                        select(StockRecord)
                        .where(StockRecord.variant_id == res.variant_id)
                        .with_for_update()
                    )
                    rec = (await db.execute(stmt2)).scalars().first()

                    if rec:
                        rec.qty_reserved -= res.qty
                        rec.qty_on_hand -= res.qty

                        # create audit log
                        movement = StockMovement(
                            variant_id=res.variant_id,
                            reason=MovementReason.SALE.value,
                            delta=-res.qty,
                            ref_order_id=order_id,
                        )
                        db.add(movement)

            await db.commit()

        elif event_type == "CheckoutCancelled":
            # reservations
            # Release reservations
            res_ids = data.get("reservations", [])
            for res_id in res_ids:
                stmt = select(Reservation).where(Reservation.id == res_id).with_for_update()
                result = await db.execute(stmt)
                res = result.scalars().first()
                if res and res.status == ReservationStatus.ACTIVE:
                    res.status = ReservationStatus.RELEASED.value
                    res.ended_at = func.now()

                    stmt2 = (
                        select(StockRecord)
                        .where(StockRecord.variant_id == res.variant_id)
                        .with_for_update()
                    )
                    rec = (await db.execute(stmt2)).scalars().first()
                    if rec:
                        rec.qty_reserved -= res.qty
            await db.commit()


async def listen():
    global pubsub
    await pubsub.subscribe("inventory_events")
    logger.info("Subscribed to inventory_events channel")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    payload = json.loads(message["data"])
                    event_type = payload.get("type")
                    data = payload.get("data", {})
                    if event_type:
                        await process_event(event_type, data)
                except Exception as e:
                    logger.error(f"Error processing event: {e}")
    except asyncio.CancelledError:
        pass


async def start_redis_listener():
    global redis_client, pubsub, listener_task
    try:
        redis_client = redis.from_url(REDIS_URL)
        pubsub = redis_client.pubsub()
        listener_task = asyncio.create_task(listen())
    except Exception as e:
        logger.error(f"Failed to start Redis listener: {e}")


async def stop_redis_listener():
    global pubsub, listener_task, redis_client
    if listener_task:
        listener_task.cancel()
    if pubsub:
        await pubsub.close()
    if redis_client:
        await redis_client.close()
