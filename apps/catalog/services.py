"""Catalog query services (C-2, C-3).

Encapsulates the filtered, sorted, and searched product queryset for the
storefront listing and detail pages. Views stay thin — all query composition
lives here.
"""

from django.db import models
from django.db.models import Avg, Count, Max, Min, Q

from apps.reviews.models import ReviewStatus

from .models import Category, Product


def get_catalog_queryset(*, filters=None, sort=None, search=None):
    """Build the annotated, filtered, sorted product queryset for the shop page.

    Parameters
    ----------
    filters : dict, optional
        Accepted keys: category (slug), size, color, fit, price_min, price_max.
        Values filter via related ProductVariant axes.
    sort : str, optional
        One of: price_asc, price_desc, name_asc, name_desc, newest, popularity.
    search : str, optional
        Free-text search matching product name, description, or variant SKU.

    Returns
    -------
    QuerySet[Product]
        Active products annotated with min_price, max_price, variant_count,
        review_avg, review_count, and total_sold (for popularity sort).
    """
    if filters is None:
        filters = {}

    qs = (
        Product.objects
        .filter(is_active=True)
        .select_related("category")
        .annotate(
            # Price range across all variants for display on the product card.
            min_price=Min("variants__price_override", default=models.Value(None)),
            max_price=Max("variants__price_override", default=models.Value(None)),
            variant_count=Count("variants", distinct=True),
            # Review stats (only approved reviews render publicly — M4.5 gate).
            review_avg=Avg(
                "reviews__rating",
                filter=Q(reviews__status=ReviewStatus.APPROVED),
            ),
            review_count=Count(
                "reviews",
                filter=Q(reviews__status=ReviewStatus.APPROVED),
                distinct=True,
            ),
            # Popularity = total units sold across all variants via order items.
            total_sold=Count("variants__order_items", distinct=True),
        )
    )

    # --- Filters ---

    if category_slug := filters.get("category"):
        qs = qs.filter(category__slug=category_slug)

    # Variant-axis filters: at least one variant must match the selected axis
    # value for the product to appear. Multiple axis filters are AND-combined.
    variant_q = Q()
    if size := filters.get("size"):
        variant_q &= Q(variants__size=size)
    if color := filters.get("color"):
        variant_q &= Q(variants__color__iexact=color)
    if fit := filters.get("fit"):
        variant_q &= Q(variants__fit=fit)
    if variant_q:
        qs = qs.filter(variant_q).distinct()

    # Price range filter operates on the product's base_price because variant
    # price_override is nullable and filtering on annotations is fragile.
    if price_min := filters.get("price_min"):
        try:
            qs = qs.filter(base_price__gte=int(price_min))
        except (ValueError, TypeError):
            pass
    if price_max := filters.get("price_max"):
        try:
            qs = qs.filter(base_price__lte=int(price_max))
        except (ValueError, TypeError):
            pass

    # --- Search ---

    if search:
        search = search.strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(variants__sku__icontains=search)
            ).distinct()

    # --- Sort ---

    sort_map = {
        "price_asc": "base_price",
        "price_desc": "-base_price",
        "name_asc": "name",
        "name_desc": "-name",
        "newest": "-created_at",
        "popularity": "-total_sold",
    }
    order_by = sort_map.get(sort, "-created_at")
    qs = qs.order_by(order_by)

    return qs


def get_all_categories():
    """Return all categories for the filter sidebar."""
    return Category.objects.annotate(
        product_count=Count("products", filter=Q(products__is_active=True))
    ).order_by("name")


def get_available_colors():
    """Return distinct color values across all active product variants."""
    from .models import ProductVariant

    return list(
        ProductVariant.objects.filter(product__is_active=True)
        .values_list("color", flat=True)
        .distinct()
        .order_by("color")
    )


def get_product_detail(slug):
    """Load a single product with full variant + stock + review data for the detail page.

    Returns
    -------
    Product or None
        The product annotated with review_avg and review_count, with
        variants and their stock records prefetched. Returns None if the
        product doesn't exist or is inactive.
    """
    try:
        product = (
            Product.objects
            .filter(is_active=True, slug=slug)
            .select_related("category")
            .annotate(
                review_avg=Avg(
                    "reviews__rating",
                    filter=Q(reviews__status=ReviewStatus.APPROVED),
                ),
                review_count=Count(
                    "reviews",
                    filter=Q(reviews__status=ReviewStatus.APPROVED),
                    distinct=True,
                ),
            )
            .prefetch_related(
                models.Prefetch(
                    "variants",
                    queryset=(
                        Product.variants.rel.related_model.objects
                        .select_related("stock")
                        .order_by("size", "color", "fit")
                    ),
                ),
                models.Prefetch(
                    "reviews",
                    queryset=(
                        Product.reviews.rel.related_model.objects
                        .filter(status=ReviewStatus.APPROVED)
                        .select_related("customer")
                        .order_by("-created_at")
                    ),
                    to_attr="approved_reviews",
                ),
            )
            .get()
        )
    except Product.DoesNotExist:
        return None
    return product
