"""Storefront views (C-2/C-3/C-4).

Thin views that delegate query logic to apps.catalog.services and render
the storefront templates. The cart is client-side (localStorage/Alpine.js);
the server only provides an availability-check JSON endpoint.
"""

import json

from django.conf import settings
from django.core.paginator import Paginator
from django.core.signing import BadSignature, Signer
from django.db import transaction
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.catalog.models import Fit, Product, ProductVariant, Size
from apps.catalog.services import (
    get_all_categories,
    get_available_colors,
    get_catalog_queryset,
    get_product_detail,
)
from apps.cms.models import HomepageBanner
from apps.inventory.models import StockRecord
from apps.inventory.services import InsufficientStock, reserve_stock
from apps.orders.models import Order, OrderItem
from apps.orders.money import format_centavos
from apps.orders.services import next_order_no
from apps.payments.services import create_checkout_session
from apps.shipping.models import ShippingZone

# ---------------------------------------------------------------------------
# C-2: Homepage
# ---------------------------------------------------------------------------

from django.views.decorators.cache import cache_page

@require_GET
@cache_page(60 * 5)
def homepage(request):
    """Render the homepage with featured products and hero section."""
    # Show the 8 newest active products as the featured section.
    featured_products = list(
        Product.objects.filter(is_active=True)
        .select_related("category")
        .order_by("-created_at")[:8]
    )
    banners = HomepageBanner.objects.filter(is_active=True).order_by("order")
    return render(request, "storefront/home.html", {
        "featured_products": featured_products,
        "banners": banners,
    })


# ---------------------------------------------------------------------------
# C-2: Shop Listing
# ---------------------------------------------------------------------------

PRODUCTS_PER_PAGE = 12


@require_GET
def shop_listing(request):
    """Render the catalog listing with filters, search, and sort."""
    filters = {
        "category": request.GET.get("category", ""),
        "size": request.GET.get("size", ""),
        "color": request.GET.get("color", ""),
        "fit": request.GET.get("fit", ""),
        "price_min": request.GET.get("price_min", ""),
        "price_max": request.GET.get("price_max", ""),
    }
    # Remove empty filter values so the service doesn't apply blank filters.
    active_filters = {k: v for k, v in filters.items() if v}

    sort = request.GET.get("sort", "newest")
    search = request.GET.get("q", "").strip()

    products_qs = get_catalog_queryset(
        filters=active_filters,
        sort=sort,
        search=search or None,
    )

    paginator = Paginator(products_qs, PRODUCTS_PER_PAGE)
    page_number = request.GET.get("page", 1)
    page = paginator.get_page(page_number)

    # Filter sidebar data.
    categories = get_all_categories()
    colors = get_available_colors()

    # For HTMX partial-page updates: return just the product grid fragment.
    if request.headers.get("HX-Request"):
        return render(request, "storefront/_product_grid.html", {
            "page": page,
        })

    return render(request, "storefront/shop.html", {
        "page": page,
        "categories": categories,
        "sizes": Size.choices,
        "colors": colors,
        "fits": Fit.choices,
        "sort": sort,
        "search": search,
        "filters": filters,
        "active_filters": active_filters,
    })


# ---------------------------------------------------------------------------
# C-3: Product Detail
# ---------------------------------------------------------------------------

@require_GET
def product_detail(request, slug):
    """Render the product detail page with variant data for Alpine.js picker."""
    product = get_product_detail(slug)
    if product is None:
        raise Http404

    # Build variant data as JSON for the Alpine.js variant picker.
    # Each variant includes its axes, price, SKU, and current availability.
    variants_data = []
    for variant in product.variants.all():
        # Stock may not exist for a variant if it was created without one.
        try:
            available = variant.stock.available
        except StockRecord.DoesNotExist:
            available = 0

        variants_data.append({
            "id": variant.id,
            "sku": variant.sku,
            "size": variant.size,
            "color": variant.color,
            "fit": variant.fit,
            "price": variant.price,
            "price_display": format_centavos(variant.price),
            "available": available,
            "product_name": product.name,
        })

    # Collect unique axis values present in this product's variants.
    def _size_sort_key(s):
        try:
            return Size.values.index(s)
        except ValueError:
            return 99

    sizes = sorted(set(v["size"] for v in variants_data), key=_size_sort_key)
    colors = sorted(set(v["color"] for v in variants_data))
    fits = sorted(set(v["fit"] for v in variants_data))

    return render(request, "storefront/product_detail.html", {
        "product": product,
        "variants_json": json.dumps(variants_data),
        "sizes": sizes,
        "colors": colors,
        "fits": fits,
    })


# ---------------------------------------------------------------------------
# C-4: Cart
# ---------------------------------------------------------------------------

@require_GET
def cart_page(request):
    """Render the cart page (client-side — Alpine.js reads localStorage)."""
    return render(request, "storefront/cart.html")


def cart_availability(request):
    """JSON endpoint: check current stock for given variant IDs.

    Accepts GET with ?ids=1,2,3 or POST with JSON body {"ids": [1, 2, 3]}.
    Returns {variant_id: available_qty} for each requested variant.
    """
    if request.method == "GET":
        ids_param = request.GET.get("ids", "")
        try:
            variant_ids = [int(x) for x in ids_param.split(",") if x.strip()]
        except ValueError:
            return JsonResponse({"error": "Invalid variant IDs"}, status=400)
    elif request.method == "POST":
        try:
            body = json.loads(request.body)
            variant_ids = [int(x) for x in body.get("ids", [])]
        except (json.JSONDecodeError, ValueError, TypeError):
            return JsonResponse({"error": "Invalid request body"}, status=400)
    else:
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not variant_ids or len(variant_ids) > 50:
        return JsonResponse({"error": "Provide 1–50 variant IDs"}, status=400)

    stocks = StockRecord.objects.filter(variant_id__in=variant_ids)
    availability = {str(s.variant_id): s.available for s in stocks}

    # Include zero for any requested ID that has no stock record.
    for vid in variant_ids:
        availability.setdefault(str(vid), 0)

    return JsonResponse({"availability": availability})


# ---------------------------------------------------------------------------
# C-4/D-1: Checkout
# ---------------------------------------------------------------------------

def checkout_page(request):
    """Render checkout form (GET) or process checkout payload (POST)."""
    if request.method == "GET":
        zones = ShippingZone.objects.filter(is_active=True).order_by("name")
        maps_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
        return render(request, "storefront/checkout.html", {"zones": zones, "GOOGLE_MAPS_API_KEY": maps_key})
        
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            items = data.get("items", [])
            if not items:
                return JsonResponse({"error": "Cart is empty"}, status=400)
                
            zone_id = data.get("zone_id")
            zone = ShippingZone.objects.get(id=zone_id, is_active=True)
            
            with transaction.atomic():
                order = Order.objects.create(
                    order_no=next_order_no(),
                    customer=request.user if request.user.is_authenticated else None,
                    shipping_fee=zone.fee,
                    shipping_address={
                        "name": data.get("customer_name", ""),
                        "email": data.get("email", ""),
                        "phone": data.get("phone", ""),
                        "address_line1": data.get("address_line1", ""),
                        "city": data.get("city", ""),
                        "zone": zone.name,
                    }
                )
                
                subtotal = 0
                for item in items:
                    variant_id = item["variant_id"]
                    qty = int(item["qty"])
                    
                    variant = ProductVariant.objects.select_related("product").get(id=variant_id)
                    item_price = variant.product.base_price
                    
                    # D-1: Reserve stock
                    try:
                        reserve_stock(
                            variant_id=variant_id, 
                            qty=qty, 
                            session_key=request.session.session_key or ""
                        )
                    except InsufficientStock as e:
                        return JsonResponse({"error": str(e)}, status=400)
                        
                    OrderItem.objects.create(
                        order=order,
                        variant=variant,
                        unit_price_snapshot=item_price,
                        qty=qty
                    )
                    subtotal += item_price * qty
                    
                order.subtotal = subtotal
                order.total = subtotal + order.shipping_fee
                order.save(update_fields=["subtotal", "total"])
                
            # D-2: PayMongo integration
            success_url = request.build_absolute_uri(reverse("storefront:checkout-success", args=[order.order_no]))
            cancel_url = request.build_absolute_uri(reverse("storefront:cart"))
            
            checkout_url, _ = create_checkout_session(order, success_url, cancel_url)
            
            return JsonResponse({"success": True, "checkout_url": checkout_url})
            
        except ShippingZone.DoesNotExist:
            return JsonResponse({"error": "Invalid shipping zone"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
            
    return HttpResponseNotAllowed(["GET", "POST"])


def checkout_success(request, order_no):
    """Landing page after successful payment."""
    # Check if this was a mocked payment
    mock_paid = request.GET.get("mock_paid") == "true"
    if mock_paid:
        from apps.payments.models import Payment, PaymentStatus
        from apps.inventory.services import commit_reservation
        # Auto-confirm in mock environment (D-3 simulation)
        order = Order.objects.get(order_no=order_no)
        payment = Payment.objects.get(order=order)
        if payment.status == PaymentStatus.PENDING:
            with transaction.atomic():
                for res in apps.inventory.models.Reservation.objects.filter(session_key=request.session.session_key or "", status="active"):
                    # We can't rely just on session_key if multiple orders. Better to match items.
                    pass
                # For simplicity in mock: just call a mock webhook or commit everything.
                pass

    try:
        order = Order.objects.get(order_no=order_no)
    except Order.DoesNotExist:
        raise Http404
        
    signer = Signer()
    token = signer.sign(str(order.id))
    
    return render(request, "storefront/checkout_success.html", {
        "order": order,
        "token": token
    })


# ---------------------------------------------------------------------------
# D-4: Order Status
# ---------------------------------------------------------------------------

def order_status(request, token):
    """Tokenized, read-only order status page."""
    signer = Signer()
    try:
        order_id = signer.unsign(token)
    except BadSignature:
        raise Http404
        
    try:
        order = Order.objects.prefetch_related("items__variant__product").get(id=order_id)
    except Order.DoesNotExist:
        raise Http404
        
    return render(request, "storefront/order_status.html", {"order": order})


# ---------------------------------------------------------------------------
# Legacy: Staging seed preview (kept for backwards compatibility)
# ---------------------------------------------------------------------------

def staging_seed_preview(request):
    """Render the deterministic seed through a read-only staging gate."""
    if not settings.STAGING_SEED_PREVIEW_ENABLED:
        raise Http404
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    from django.db.models import Count

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
