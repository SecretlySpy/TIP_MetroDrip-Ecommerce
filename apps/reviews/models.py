"""Reviews & ratings (§4, FR-17): verified purchase only, moderated.

Nothing with status != approved may ever render publicly (M4.5 gate) — public
querysets must always filter on ReviewStatus.APPROVED.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ReviewStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Review(models.Model):
    customer = models.ForeignKey(
        "accounts.Customer", on_delete=models.CASCADE, related_name="reviews"
    )
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="reviews")
    # Proof of purchase (FR-17): submission-time validation checks this order is
    # the customer's, is Delivered, and contains the product. PROTECT keeps the
    # evidence — an order with a review on it can't be hard-deleted.
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="reviews")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    body = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Validators improve form errors, while this database check also
            # protects imports, scripts, and any future bulk-write path.
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="chk_review_rating_1_to_5",
            ),
            # One review per product per customer; re-reviewing edits, not duplicates.
            models.UniqueConstraint(fields=["customer", "product"], name="uniq_customer_review"),
        ]

    def __str__(self):
        return f"{self.product_id} {self.rating}★ by {self.customer_id} ({self.status})"
