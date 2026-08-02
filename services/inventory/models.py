import datetime
import enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)

from .database import Base

# Must replicate the invariants of the Django app: InnoDB, utf8mb4, utf8mb4_0900_ai_ci.
table_args = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class ReservationStatus(enum.StrEnum):
    ACTIVE = "active"
    COMMITTED = "committed"
    RELEASED = "released"
    EXPIRED = "expired"


class MovementReason(enum.StrEnum):
    SALE = "sale"
    RESTOCK = "restock"
    ADJUSTMENT = "adjustment"


class StockRecord(Base):
    __tablename__ = "inventory_stockrecord"
    __table_args__ = (
        CheckConstraint("qty_reserved <= qty_on_hand", name="chk_reserved_lte_on_hand"),
        table_args,
    )

    # We don't have the catalog ProductVariant model here, so we store the variant_id
    # directly as an integer.
    variant_id = Column(Integer, primary_key=True, autoincrement=False)
    qty_on_hand = Column(Integer, default=0, nullable=False)
    qty_reserved = Column(Integer, default=0, nullable=False)
    low_stock_threshold = Column(Integer, default=5, nullable=False)

    @property
    def available(self):
        return self.qty_on_hand - self.qty_reserved


class Reservation(Base):
    __tablename__ = "inventory_reservation"
    __table_args__ = (
        Index("idx_res_status_expiry", "status", "expires_at"),
        CheckConstraint("qty >= 1", name="chk_reservation_qty_min1"),
        table_args,
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    variant_id = Column(
        Integer, ForeignKey("inventory_stockrecord.variant_id", ondelete="RESTRICT"), nullable=False
    )
    qty = Column(Integer, nullable=False)
    status = Column(String(9), default=ReservationStatus.ACTIVE.value, nullable=False)
    session_key = Column(String(64), default="", nullable=False)

    # We just store order_id here without foreign key because orders are in a different DB
    order_id = Column(Integer, nullable=True)

    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)


class StockMovement(Base):
    __tablename__ = "inventory_stockmovement"
    __table_args__ = (CheckConstraint("qty > 0", name="chk_stockmovement_qty_min1"), table_args)

    id = Column(Integer, primary_key=True, autoincrement=True)
    variant_id = Column(
        Integer, ForeignKey("inventory_stockrecord.variant_id", ondelete="RESTRICT"), nullable=False
    )
    reason = Column(String(12), nullable=False)
    delta = Column(Integer, nullable=False)
    ref_order_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
