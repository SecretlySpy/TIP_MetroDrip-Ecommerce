"""Catalog query services (C-2, C-3).

Encapsulates the filtered, sorted, and searched product queryset for the
storefront listing and detail pages. Views stay thin — all query composition
lives here.
"""

from django.db import models
from django.db.models import Count, Max, Min, Q

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
        Product.objects.filter(is_active=True)
        .select_related("category")
        .annotate(
            # Price range across all variants for display on the product card.
            min_price=Min("variants__price_override", default=models.Value(None)),
            max_price=Max("variants__price_override", default=models.Value(None)),
            variant_count=Count("variants", distinct=True),
        )
    )

    # Owner APIs return grouped values; no SQL crosses service schemas.
    from apps.orders.read_api import product_sales
    from apps.reviews.read_api import product_statistics

    stats = product_statistics()
    sold = product_sales()
    qs = qs.annotate(
        review_avg=_metric_case(
            {key: value["average"] for key, value in stats.items()}, models.FloatField(), None
        ),
        review_count=_metric_case(
            {key: value["count"] for key, value in stats.items()}, models.IntegerField(), 0
        ),
        total_sold=_metric_case(sold, models.IntegerField(), 0),
    )

    # --- Filters ---

    # A main-category slug spans the whole branch: products pinned directly to
    # the root (legacy assignments predating the hierarchy) plus everything in
    # its children. A child slug only matches the first half of the OR, because
    # the taxonomy is capped at two levels so children have no children.
    if category_slug := filters.get("category"):
        qs = qs.filter(
            Q(category__slug=category_slug) | Q(category__parent__slug=category_slug)
        ).distinct()

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
        # Ignore malformed optional filters instead of failing the listing page.
        except (ValueError, TypeError):
            pass
    if price_max := filters.get("price_max"):
        try:
            qs = qs.filter(base_price__lte=int(price_max))
        # Ignore malformed optional filters instead of failing the listing page.
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


def get_category_tree():
    """Return main categories with their children, for navigation and filters.

    Exactly two queries regardless of taxonomy size: one for the roots, one for
    the prefetched children. Both carry an active-product count, so templates
    can render counts without touching the database.

    Returns
    -------
    list[Category]
        Roots ordered by name. Each carries:
        `child_categories`  — its children, ordered by name, each annotated
                              with `product_count`;
        `product_count`     — products assigned directly to the root;
        `total_product_count` — the root plus every child, matching what a
                              click on the main category actually lists.
    """
    active_products = Count("products", filter=Q(products__is_active=True))

    children = (
        Category.objects.filter(parent__isnull=False)
        .annotate(product_count=active_products)
        .order_by("name")
    )

    roots = list(
        Category.objects.filter(parent__isnull=True)
        .annotate(product_count=active_products)
        .prefetch_related(
            models.Prefetch("children", queryset=children, to_attr="child_categories")
        )
        .order_by("name")
    )

    # Summed in Python from already-prefetched rows; a database-side rollup
    # would need a third query or a correlated subquery per root.
    for root in roots:
        root.total_product_count = root.product_count + sum(
            child.product_count for child in root.child_categories
        )

    return roots


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
            Product.objects.filter(is_active=True, slug=slug)
            .select_related("category")
            .prefetch_related(
                models.Prefetch(
                    "variants",
                    queryset=(
                        Product.variants.rel.related_model.objects.select_related("stock").order_by(
                            "size", "color", "fit"
                        )
                    ),
                ),
            )
            .get()
        )
    except Product.DoesNotExist:
        return None
    from apps.reviews.read_api import approved_reviews, product_statistics

    stats = product_statistics([product.pk]).get(product.pk, {"average": None, "count": 0})
    product.review_avg = stats["average"]
    product.review_count = stats["count"]
    product.approved_reviews = approved_reviews(product.pk)
    return product


def _metric_case(values, field, default):
    """Compose local catalog annotations from owner-provided scalar data."""
    if not values:
        return models.Value(default, output_field=field)
    return models.Case(
        *(models.When(pk=key, then=models.Value(value)) for key, value in values.items()),
        default=models.Value(default),
        output_field=field,
    )
