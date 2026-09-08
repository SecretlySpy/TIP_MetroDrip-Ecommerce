"""Orders-owned scalar projections; Catalog never joins order tables."""

from django.db.models import Count

from .models import OrderItem


def product_sales():
    # Preserve the existing popularity metric (purchased lines, not revenue).
    return {row["product_ref"]: row["count"] for row in
            OrderItem.objects.values("product_ref").annotate(count=Count("pk"))}
