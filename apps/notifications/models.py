"""Mobile push-notification persistence (Epic H: FR-27/FR-28).

DeviceToken maps a customer to their Expo push token(s); Notification is the
server-side record behind the in-app notification centre, mirroring every
delivered push so read/unread state survives reinstalls.
"""

from django.conf import settings
from django.db import models

from apps.core.lifecycle import service_cascade, service_set_null


class DevicePlatform(models.TextChoices):
    IOS = "ios", "iOS"
    ANDROID = "android", "Android"


class DeviceToken(models.Model):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        db_column="customer_ref",
        on_delete=service_cascade,
        related_name="device_tokens",
    )
    # Expo push tokens are opaque strings, unique per app install.
    token = models.CharField(max_length=200, unique=True)
    platform = models.CharField(max_length=10, choices=DevicePlatform.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.customer_id} {self.platform} …{self.token[-8:]}"

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(platform__in=["ios", "android"]), name="chk_device_platform"
            ),
        ]


class NotificationCategory(models.TextChoices):
    ORDER = "order", "Order update"
    DROP = "drop", "New drop"
    STOCK = "stock", "Back in stock"
    REVIEW = "review", "Review reminder"


class Notification(models.Model):
    """One row per delivered (or attempted) push, per customer (FR-28)."""

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        db_column="customer_ref",
        on_delete=service_cascade,
        related_name="notifications",
    )
    title = models.CharField(max_length=140)
    body = models.TextField(blank=True)
    category = models.CharField(
        max_length=10, choices=NotificationCategory.choices, default=NotificationCategory.ORDER
    )
    # Optional deep-link target for order events.
    order = models.ForeignKey(
        "orders.Order",
        db_constraint=False,
        db_column="order_ref",
        null=True,
        blank=True,
        on_delete=service_set_null,
        related_name="+",
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(category__in=["order", "drop", "stock", "review"]),
                name="chk_notification_category",
            ),
        ]
        ordering = ["-created_at"]
        indexes = [
            # The centre's hot query: this customer's unread, newest first.
            models.Index(fields=["customer", "is_read", "-created_at"], name="idx_notif_inbox"),
        ]

    def __str__(self):
        return f"{self.customer_id}: {self.title} ({'read' if self.is_read else 'unread'})"
