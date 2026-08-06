import datetime
import enum

from sqlalchemy import (
    JSON,
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
    # Django's MovementReason has always had this (apps/inventory/models.py); its
    # absence here meant a returned item could be written by the monolith and
    # then fail to round-trip through the service's own enum.
    RETURN = "return"


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
    # The caller's identity for this hold group. Every mutation addresses a
    # reservation through this, never through an id this service minted, so a
    # caller can compensate for a request whose outcome it never learned.
    checkout_id = Column(String(64), default="", nullable=False, index=True)

    # order_id carries no foreign key: Orders is a separate bounded context and
    # the link is owned by its StockHold row, not by this table.
    order_id = Column(Integer, nullable=True)

    expires_at = Column(DateTime, nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.UTC), nullable=False
    )
    ended_at = Column(DateTime, nullable=True)


class StockMovement(Base):
    __tablename__ = "inventory_stockmovement"
    # The constraint here used to read `qty > 0` on a table that has no `qty`
    # column — a copy-paste from Reservation. It was never caught because
    # SKIP_CREATE_ALL meant it was rarely emitted, which is exactly the class of
    # drift that having two schema authorities over one table name produces.
    # Django owns this DDL (chk_movement_reason_delta); nothing is declared here.
    __table_args__ = (table_args,)

    id = Column(Integer, primary_key=True, autoincrement=True)
    variant_id = Column(
        Integer, ForeignKey("inventory_stockrecord.variant_id", ondelete="RESTRICT"), nullable=False
    )
    reason = Column(String(12), nullable=False)
    delta = Column(Integer, nullable=False)
    ref_order_id = Column(Integer, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.UTC), nullable=False
    )


class IdempotencyRecord(Base):
    """Mirrors `apps.inventory.models.IdempotencyRecord`; Django owns the DDL.

    The guarantee is in the *ordering*, not the table: this row and the stock
    mutation it guards are inserted in one transaction, so a key present with a
    terminal status means the mutation was applied. There is no window where
    one exists without the other.
    """

    __tablename__ = "inventory_idempotencyrecord"
    __table_args__ = (table_args,)

    key_hash = Column(String(64), primary_key=True, autoincrement=False)
    request_fingerprint = Column(String(64), nullable=False)
    # 0 means "claimed but not yet committed" — a concurrent caller must wait
    # rather than assume either outcome.
    status_code = Column(Integer, default=0, nullable=False)
    response_body = Column(JSON, nullable=False, default=dict)
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.UTC), nullable=False
    )
