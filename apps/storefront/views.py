"""Temporary staging-only visibility before the real storefront is built."""

from django.conf import settings
from django.db.models import Count
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import render

from apps.catalog.models import Product


def staging_seed_preview(request):
    """Render the deterministic seed through a read-only staging gate."""
    if not settings.STAGING_SEED_PREVIEW_ENABLED:
        # A 404 reveals no hidden staging surface in development or production.
        raise Http404
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    products = list(
        Product.objects.filter(is_active=True)
        .select_related("category")
        .annotate(variant_count=Count("variants"))
        .order_by("name")
    )
    total_variants = sum(product.variant_count for product in products)

    return render(
        request,
        "staging/seed_preview.html",
        {
            "products": products,
            "product_count": len(products),
            "total_variants": total_variants,
        },
    )
