"""Orders domain (§4) with the enforced state machine (Hard Invariant 5).

Status changes MUST go through Order.transition_to(); model and queryset guards
reject normal ORM bypasses. Money fields are integer centavos (Hard Invariant 2).
"""

from django.conf import settings
from django.db import models, transaction


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    PACKED = "packed", "Packed"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"


# The only legal edges (Invariant 5). Cancel is for never-paid orders; anything
# already paid exits via Refunded (E-4 restores stock with a `return` movement).
ALLOWED_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.PACKED, OrderStatus.REFUNDED},
    OrderStatus.PACKED: {OrderStatus.SHIPPED, OrderStatus.REFUNDED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED, OrderStatus.REFUNDED},
    OrderStatus.DELIVERED: {OrderStatus.REFUNDED},
    OrderStatus.CANCELLED: set(),
    OrderStatus.REFUNDED: set(),
}

# The locked public format has exactly five sequence digits per calendar year.
MAX_ORDER_SEQUENCE = 99_999


class IllegalTransition(Exception):
    """Raised on any state change not in ALLOWED_TRANSITIONS (Invariant 5)."""


class OrderQuerySet(models.QuerySet):
    """Block bulk APIs that would bypass the order state machine."""

    def update(self, **kwargs):
        if "status" in kwargs:
            raise IllegalTransition("Order status changes must use transition_to().")
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if "status" in fields:
            raise IllegalTransition("Order status changes must use transition_to().")
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        # Every order begins Pending. Without this guard, bulk_create() would
        # bypass Model.save() and could fabricate paid or fulfilled orders.
        objects = list(objs)
        try:
            has_non_pending_order = any(
                OrderStatus(obj.status) != OrderStatus.PENDING for obj in objects
            )
        except ValueError as exc:
            raise IllegalTransition("New orders require a recognized status.") from exc
        if has_non_pending_order:
            raise IllegalTransition("New orders must start in Pending status.")

        # MySQL's conflict-update mode can mutate an existing row rather than
        # insert a new one, so status must never participate in that update list.
        updated_field_names = update_fields or ()
        if update_conflicts and "status" in updated_field_names:
            raise IllegalTransition("Conflict updates cannot modify order status.")
        return super().bulk_create(
            objects,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )


class OrderManager(models.Manager.from_queryset(OrderQuerySet)):
    """Default manager carrying the state-machine bulk-write protections."""


class Order(models.Model):
    # Format MD-YYYY-NNNNN, allocated race-safely by services.next_order_no().
    order_no = models.CharField(max_length=20, unique=True)
    # NULL = guest order (D-05). SET_NULL so account erasure (RA 10173) never
    # destroys the commercial record.
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    status = models.CharField(
        max_length=10, choices=OrderStatus.choices, default=OrderStatus.PENDING
    )
    # Integer centavos, always (Invariant 2).
    subtotal = models.PositiveIntegerField(default=0)
    shipping_fee = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    # Snapshot of the full ship-to block, including contact email/phone —
    # guest orders have no customer row, so contact data must live here.
    shipping_address = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OrderManager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Persisted totals must reconcile exactly in integer centavos.
            models.CheckConstraint(
                condition=models.Q(total=models.F("subtotal") + models.F("shipping_fee")),
                name="chk_order_total_reconciles",
            ),
        ]

    def __str__(self):
        return self.order_no

    def save(self, *args, **kwargs):
        """Persist an order while rejecting direct status assignment."""
        if self._state.adding:
            try:
                initial_status = OrderStatus(self.status)
            except ValueError as exc:
                raise IllegalTransition("New orders require a recognized status.") from exc
            if initial_status != OrderStatus.PENDING:
                raise IllegalTransition("New orders must start in Pending status.")
            return super().save(*args, **kwargs)

        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "status" not in update_fields:
            # An explicit field list that omits status cannot overwrite a newer
            # state, so ordinary maintenance can proceed without a row lock.
            return super().save(*args, **kwargs)

        database = kwargs.get("using") or self._state.db or "default"
        with transaction.atomic(using=database):
            # Locking closes the stale-read race for save() calls that write all
            # fields. A concurrent transition must finish before this comparison.
            stored_status = (
                type(self)
                ._base_manager.using(database)
                .select_for_update()
                .values_list("status", flat=True)
                .get(pk=self.pk)
            )
            if self.status != stored_status:
                raise IllegalTransition("Order status changes must use transition_to().")

            return super().save(*args, **kwargs)

    def transition_to(self, new_status):
        """Lock, validate, and persist one legal state transition atomically."""
        if self._state.adding:
            raise IllegalTransition("An unsaved order cannot transition status.")

        try:
            target = OrderStatus(new_status)
        except ValueError as exc:
            raise IllegalTransition(f"Unknown order status: {new_status}") from exc

        database = self._state.db or "default"
        with transaction.atomic(using=database):
            # A fresh row lock prevents two workers from validating against the
            # same stale status and committing incompatible next states.
            locked = type(self).objects.using(database).select_for_update().get(pk=self.pk)
            current = OrderStatus(locked.status)
            if target not in ALLOWED_TRANSITIONS[current]:
                raise IllegalTransition(f"{locked.order_no}: {current} → {target} is not allowed")

            locked.status = target
            # Calling the parent implementation is private to this validated,
            # locked path; no caller-controlled bypass flag is exposed on save().
            super(Order, locked).save(using=database, update_fields=["status"])

        # Keep the caller usable even if it was stale before the locked read.
        self.status = target
        return self


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # PROTECT: a variant that has ever been sold must never be hard-deleted,
    # or order history and the movement ledger lose their reference.
    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.PROTECT, related_name="order_items"
    )
    qty = models.PositiveIntegerField()
    # Price at purchase time (centavos) — later catalog edits must not rewrite
    # historical orders.
    unit_price_snapshot = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(qty__gte=1), name="chk_order_item_qty_gte_1"),
            # The cart merges duplicate lines; one row per SKU per order.
            models.UniqueConstraint(fields=["order", "variant"], name="uniq_order_line"),
        ]

    def __str__(self):
        return f"{self.order_id} × {self.variant_id} ({self.qty})"


class OrderNumberSequence(models.Model):
    """Per-year counter backing MD-YYYY-NNNNN allocation.

    A dedicated row locked with select_for_update makes numbering race-safe;
    deriving MAX(order_no)+1 would collide under concurrent checkouts.
    """

    year = models.PositiveIntegerField(unique=True)
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(year__gte=1000, year__lte=9999),
                name="chk_order_sequence_four_digit_year",
            ),
            models.CheckConstraint(
                condition=models.Q(last_value__lte=MAX_ORDER_SEQUENCE),
                name="chk_order_sequence_max_99999",
            ),
        ]

    def __str__(self):
        return f"{self.year}: {self.last_value}"
