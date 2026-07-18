"""Payment record per order (§4). One Order = one Payment row.

Status here mirrors what signature-verified PayMongo webhooks tell us (Hard
Invariant 3) — client redirects never write to this table.
"""

from django.db import models


class PaymentMethod(models.TextChoices):
    CARD = "card", "Card"
    GCASH = "gcash", "GCash"
    MAYA = "maya", "Maya"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"


class Payment(models.Model):
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="payment")
    # PayMongo's identifier — the join key for reconciliation and idempotent
    # webhook replay (M5 gate: reconciles to the centavo).
    # NULL permits multiple not-yet-created provider sessions, while unique
    # non-NULL values make a PayMongo object an unambiguous reconciliation key.
    provider_ref = models.CharField(max_length=128, null=True, blank=True, unique=True)
    method = models.CharField(max_length=8, choices=PaymentMethod.choices)
    status = models.CharField(
        max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    amount = models.PositiveIntegerField()  # MySQL INT centavos (Invariant 2)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.order_id} {self.method} {self.status}"
