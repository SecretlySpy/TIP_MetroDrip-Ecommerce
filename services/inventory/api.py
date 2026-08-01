import datetime
from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from .database import get_db
from .models import StockRecord, Reservation, ReservationStatus

router = APIRouter()


@router.get("/stock/{variant_id}")
async def get_stock(variant_id: int, db: AsyncSession = Depends(get_db)):
    record = await db.get(StockRecord, variant_id)
    if not record:
        raise HTTPException(status_code=404, detail="StockRecord not found")
    return {
        "variant_id": record.variant_id,
        "qty_on_hand": record.qty_on_hand,
        "qty_reserved": record.qty_reserved,
        "low_stock_threshold": record.low_stock_threshold,
        "available": record.available
    }


@router.post("/reservations")
async def create_reservations(items: List[Dict[str, int]], session_key: str = "", db: AsyncSession = Depends(get_db)):
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
                expires_at=expires_at,
                status=ReservationStatus.ACTIVE
            )
            db.add(res)
            created.append(res)
            
        await db.commit()
        return {"status": "success", "reservations": [r.id for r in created]}
        
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
