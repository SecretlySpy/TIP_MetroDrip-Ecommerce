"""Orders-owned review projections for the cohosted Catalog/BFF callers."""

from django.db.models import Avg, Count

from .models import Review, ReviewStatus


def product_statistics(product_ids=None):
    query = Review.objects.filter(status=ReviewStatus.APPROVED)
    if product_ids is not None:
        query = query.filter(product_id__in=product_ids)
    return {
        row["product_id"]: {"average": row["average"], "count": row["count"]}
        for row in query.values("product_id").annotate(average=Avg("rating"), count=Count("pk"))
    }


def approved_reviews(product_id):
    return list(Review.objects.filter(product_id=product_id, status=ReviewStatus.APPROVED)
                .prefetch_related("customer").order_by("-created_at"))
