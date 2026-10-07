"""Each schema owns its own durable lifecycle-event queue."""

from django.db import models
from django.utils import timezone


class ServiceEvent(models.Model):
    target_model = models.CharField(max_length=100)
    target_field = models.CharField(max_length=100)
    reference_id = models.BigIntegerField()
    operation = models.CharField(max_length=8)
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(operation__in=["delete", "set_null"]),
                name="chk_service_event_operation",
            ),
        ]
        indexes = [models.Index(fields=["completed_at", "id"], name="idx_service_event_pending")]

    def __str__(self):
        return f"{self.operation} {self.target_model}.{self.target_field}={self.reference_id}"
