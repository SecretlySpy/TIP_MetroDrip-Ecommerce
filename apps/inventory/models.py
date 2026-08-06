"""Inventory domain (§4, Hard Invariants 1 & 4).

StockRecord holds the two counters that define availability; StockMovement is
the append-only audit trail. Epic B-1 will add the only operational mutation
service using transaction.atomic() + select_for_update(). Task A-2 writes only
atomic initial seed balances and their matching restock movements.
"""

from django.db import models


class StockRecord(models.Model):
    """Single-warehouse stock counters for one SKU (variant)."""

    variant = models.OneToOneField(
        "catalog.ProductVariant", on_delete=models.CASCADE, related_name="stock"
    )
    qty_on_hand = models.PositiveIntegerField(default=0)
    # Units held by active checkout reservations (15-min TTL, FR-5); still on
    # hand physically, but not sellable.
    qty_reserved = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)

    class Meta:
        constraints = [
            # DB-level backstop for Invariant 1: reservations can never exceed
            # physical stock even if application code regresses. MySQL 8.0.16+
            # enforces CHECK constraints.
            models.CheckConstraint(
                condition=models.Q(qty_reserved__lte=models.F("qty_on_hand")),
                name="chk_reserved_lte_on_hand",
            ),
        ]

    def __str__(self):
        return f"{self.variant_id}: {self.qty_on_hand} on hand / {self.qty_reserved} reserved"

    @property
    def available(self):
        """Invariant 1: available = qty_on_hand − qty_reserved."""
        return self.qty_on_hand - self.qty_reserved


class ReservationStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    COMMITTED = "committed", "Committed"
    RELEASED = "released", "Released"
    EXPIRED = "expired", "Expired"


class Reservation(models.Model):
    """A 15-minute checkout hold on units of one SKU (FR-5).

    Lifecycle: ACTIVE → COMMITTED (payment confirmed, becomes a sale movement)
    | RELEASED (checkout abandoned/cancelled explicitly) | EXPIRED (TTL sweep).
    The three non-active states are terminal. Reservations never change
    qty_on_hand — only qty_reserved — so they never write StockMovement rows.
    """

    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.PROTECT, related_name="reservations"
    )
    qty = models.PositiveIntegerField()
    status = models.CharField(
        max_length=9, choices=ReservationStatus.choices, default=ReservationStatus.ACTIVE
    )
    # Correlates the hold with a checkout session before an Order exists (D-1).
    session_key = models.CharField(max_length=64, blank=True, default="")
    # Groups every hold placed by one checkout attempt, and is the identity that
    # crosses the service boundary (ADR-P3-003 step 3). Minted before any write,
    # so it exists while the Order still does not — which is what lets stock be
    # reserved *before* the order row and compensated by a caller that never has
    # to reach into the ledger's own tables to find what it created.
    checkout_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    # Set when the hold converts into a sale; SET_NULL because a reservation is
    # operational state, not audit evidence (StockMovement carries the audit).
    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reservations",
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    # When the row left ACTIVE, regardless of which terminal state it entered.
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            # The sweep's hot query: WHERE status = active AND expires_at <= now.
            models.Index(fields=["status", "expires_at"], name="idx_res_status_expiry"),
        ]
        constraints = [
            # A zero-unit hold is meaningless and would let bad input mask bugs.
            models.CheckConstraint(condition=models.Q(qty__gte=1), name="chk_reservation_qty_min1"),
        ]

    def __str__(self):
        return f"{self.variant_id} × {self.qty} ({self.status})"


class IdempotencyRecord(models.Model):
    """Makes a retried stock mutation safe to replay.

    Under synchronous REST a read timeout is indistinguishable from success:
    the request was sent, so the mutation may or may not have been applied
    (`ServiceUncertain` in `apps/core/http.py`). Without a replay guard the
    only safe response is to give up and compensate, which turns every blip
    into a lost checkout.

    The guarantee comes from *ordering*, not from the table itself: the key row
    and the stock mutation are written in one transaction, so "key present with
    a terminal status" is true exactly when the mutation was applied. There is
    no window in which one exists without the other.

    Django owns this DDL even though the service writes the rows — one schema
    authority, per ADR-P3-013's shared-schema/exclusive-writer decision.
    """

    #: sha256(f"{route}:{key}") — hashed so an opaque client key of any shape
    #: fits a fixed-width primary key and never lands in a log verbatim.
    key_hash = models.CharField(max_length=64, primary_key=True)
    #: sha256 of the canonical request body. A second call with the same key but
    #: a different body is a client bug, not a retry, and must not replay.
    request_fingerprint = models.CharField(max_length=64)
    #: 0 means "in flight" — claimed by a request that has not yet committed.
    status_code = models.PositiveSmallIntegerField(default=0)
    response_body = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "idempotency record"
        verbose_name_plural = "idempotency records"

    def __str__(self):
        return f"{self.key_hash[:12]}… → {self.status_code or 'in flight'}"


class MovementReason(models.TextChoices):
    SALE = "sale", "Sale"
    RESTOCK = "restock", "Restock"
    ADJUSTMENT = "adjustment", "Adjustment"
    RETURN = "return", "Return"


class AppendOnlyMovementQuerySet(models.QuerySet):
    """Reject ORM operations that would rewrite or erase audit history."""

    def update(self, **kwargs):
        raise TypeError("StockMovement is append-only; rows cannot be updated.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise TypeError("StockMovement is append-only; rows cannot be bulk-updated.")

    def delete(self):
        raise TypeError("StockMovement is append-only; rows cannot be deleted.")

    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        # Plain bulk inserts are still append-only. Conflict-update mode is not:
        # MySQL would translate it to ON DUPLICATE KEY UPDATE and rewrite history.
        if update_conflicts:
            raise TypeError("StockMovement conflict updates are forbidden.")
        return super().bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )


class StockMovementManager(models.Manager.from_queryset(AppendOnlyMovementQuerySet)):
    """Expose creation and reads while inheriting append-only queryset guards."""


class StockMovement(models.Model):
    """Append-only ledger of every qty_on_hand change (Invariant 4).

    Reservations are NOT movements — they don't change qty_on_hand; only the
    sale that consumes one does.
    """

    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.PROTECT, related_name="movements"
    )
    delta = models.IntegerField()  # signed: sale −n, restock +n
    reason = models.CharField(max_length=12, choices=MovementReason.choices)
    ref_order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.PROTECT, related_name="movements"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = StockMovementManager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # The sign must agree with the business event. Adjustments may move
            # either direction, but a zero-delta row would not be a movement.
            models.CheckConstraint(
                condition=(
                    (models.Q(reason=MovementReason.SALE) & models.Q(delta__lt=0))
                    | (models.Q(reason=MovementReason.RESTOCK) & models.Q(delta__gt=0))
                    | (models.Q(reason=MovementReason.RETURN) & models.Q(delta__gt=0))
                    | (models.Q(reason=MovementReason.ADJUSTMENT) & ~models.Q(delta=0))
                ),
                name="chk_movement_reason_delta",
            ),
        ]

    def __str__(self):
        return f"{self.variant_id} {self.delta:+d} ({self.reason})"

    # -- Append-only enforcement: a ledger you can edit is not an audit log. --
    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise TypeError("StockMovement is append-only; rows cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("StockMovement is append-only; rows cannot be deleted.")
