"""Storefront views (C-2/C-3/C-4, D-1/D-4).

Thin views that delegate query logic to apps.catalog.services and stock/order
mutations to the domain services. The cart is client-side (localStorage +
Alpine.js); the server only exposes an availability-check JSON endpoint until
checkout, where reservations and the order are created atomically.
"""

import json
import logging

from django.conf import settings
from django.core.paginator import Paginator
from django.core.signing import BadSignature, Signer
from django.db import transaction
from django.db.models import Count
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

from apps.accounts.models import WishlistItem
from apps.catalog.models import Fit, Product, ProductVariant, Size
from apps.catalog.services import (
    get_all_categories,
    get_available_colors,
    get_catalog_queryset,
    get_product_detail,
)
from apps.cms.models import ContactMessage, HomepageBanner
from apps.inventory.models import StockRecord
from apps.inventory.services import InsufficientStock, release_reservation, reserve_stock
from apps.notifications.services import send_contact_alert, send_order_confirmation
from apps.notifications.sms import send_sms
from apps.orders.models import Order, OrderItem
from apps.orders.money import format_centavos
from apps.orders.services import next_order_no
from apps.payments.services import PayMongoError, confirm_order_paid, create_checkout_session
from apps.shipping.models import ShippingZone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# C-2: Homepage
# ---------------------------------------------------------------------------


@require_GET
@cache_page(60 * 5)  # NFR-1: catalog pages are cacheable
def homepage(request):
    """Render the homepage with hero banners and the newest active products."""
    featured_products = list(
        Product.objects.filter(is_active=True)
        .select_related("category")
        .order_by("-created_at")[:8]
    )
    banners = HomepageBanner.objects.filter(is_active=True).order_by("order")
    return render(
        request,
        "storefront/home.html",
        {"featured_products": featured_products, "banners": banners},
    )


# ---------------------------------------------------------------------------
# C-2: Shop listing
# ---------------------------------------------------------------------------

PRODUCTS_PER_PAGE = 12


@require_GET
def shop_listing(request):
    """Render the catalog listing with filters, search, and sort (FR-2)."""
    filters = {
        "category": request.GET.get("category", ""),
        "size": request.GET.get("size", ""),
        "color": request.GET.get("color", ""),
        "fit": request.GET.get("fit", ""),
        "price_min": request.GET.get("price_min", ""),
        "price_max": request.GET.get("price_max", ""),
    }
    # Blank values would otherwise be applied as filters-for-empty-string.
    active_filters = {key: value for key, value in filters.items() if value}

    sort = request.GET.get("sort", "newest")
    search = request.GET.get("q", "").strip()

    products_qs = get_catalog_queryset(filters=active_filters, sort=sort, search=search or None)

    paginator = Paginator(products_qs, PRODUCTS_PER_PAGE)
    page = paginator.get_page(request.GET.get("page", 1))

    # HTMX filter interactions swap only the grid, not the whole document.
    if request.headers.get("HX-Request"):
        return render(request, "storefront/_product_grid.html", {"page": page})

    return render(
        request,
        "storefront/shop.html",
        {
            "page": page,
            "categories": get_all_categories(),
            "sizes": Size.choices,
            "colors": get_available_colors(),
            "fits": Fit.choices,
            "sort": sort,
            "search": search,
            "filters": filters,
            "active_filters": active_filters,
        },
    )


# ---------------------------------------------------------------------------
# C-3: Product detail
# ---------------------------------------------------------------------------


@require_GET
def product_detail(request, slug):
    """Render the product detail page with variant data for the Alpine picker."""
    product = get_product_detail(slug)
    if product is None:
        raise Http404

    variants_data = []
    for variant in product.variants.all():
        try:
            available = variant.stock.available
        except StockRecord.DoesNotExist:
            # An unstocked variant renders as sold out rather than sellable.
            available = 0
        variants_data.append(
            {
                "id": variant.pk,
                "sku": variant.sku,
                "size": variant.size,
                "color": variant.color,
                "fit": variant.fit,
                "price": variant.price,
                "price_display": format_centavos(variant.price),
                "available": available,
                "product_name": product.name,
            }
        )

    def _size_sort_key(size_value):
        try:
            return Size.values.index(size_value)
        except ValueError:
            return len(Size.values)

    is_wishlisted = False
    if request.user.is_authenticated:
        is_wishlisted = WishlistItem.objects.filter(customer=request.user, product=product).exists()

    return render(
        request,
        "storefront/product_detail.html",
        {
            "product": product,
            "variants_json": json.dumps(variants_data),
            "sizes": sorted({v["size"] for v in variants_data}, key=_size_sort_key),
            "colors": sorted({v["color"] for v in variants_data}),
            "fits": sorted({v["fit"] for v in variants_data}),
            "is_wishlisted": is_wishlisted,
        },
    )


# ---------------------------------------------------------------------------
# C-4: Cart
# ---------------------------------------------------------------------------


@require_GET
def cart_page(request):
    """Render the cart shell; Alpine.js hydrates it from localStorage."""
    return render(request, "storefront/cart.html")


def cart_availability(request):
    """JSON endpoint: current availability for up to 50 variant IDs.

    GET ?ids=1,2,3 or POST {"ids": [...]} — reads only, so both are safe.
    """
    if request.method == "GET":
        try:
            variant_ids = [int(x) for x in request.GET.get("ids", "").split(",") if x.strip()]
        except ValueError:
            return JsonResponse({"error": "Invalid variant IDs"}, status=400)
    elif request.method == "POST":
        try:
            body = json.loads(request.body)
            variant_ids = [int(x) for x in body.get("ids", [])]
        except json.JSONDecodeError, ValueError, TypeError:
            return JsonResponse({"error": "Invalid request body"}, status=400)
    else:
        return HttpResponseNotAllowed(["GET", "POST"])

    if not variant_ids or len(variant_ids) > 50:
        return JsonResponse({"error": "Provide 1–50 variant IDs"}, status=400)

    availability = {
        str(stock.variant_id): stock.available
        for stock in StockRecord.objects.filter(variant_id__in=variant_ids)
    }
    for variant_id in variant_ids:
        # Unknown/unstocked IDs read as zero so stale carts self-correct.
        availability.setdefault(str(variant_id), 0)

    return JsonResponse({"availability": availability})


# ---------------------------------------------------------------------------
# D-1/D-2: Checkout
# ---------------------------------------------------------------------------

MAX_CHECKOUT_LINES = 20
MAX_LINE_QTY = 99


def _parse_checkout_items(raw_items):
    """Validate cart lines and merge duplicates; returns {variant_id: qty}."""
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Cart is empty.")
    if len(raw_items) > MAX_CHECKOUT_LINES:
        raise ValueError(f"A single order supports up to {MAX_CHECKOUT_LINES} lines.")

    quantities = {}
    for line in raw_items:
        try:
            variant_id = int(line["variant_id"])
            qty = int(line["qty"])
        except KeyError, TypeError, ValueError:
            raise ValueError("Each cart line needs a variant_id and qty.") from None
        if not 1 <= qty <= MAX_LINE_QTY:
            raise ValueError(f"Quantities must be between 1 and {MAX_LINE_QTY}.")
        quantities[variant_id] = quantities.get(variant_id, 0) + qty
    return quantities


def checkout_page(request):
    """Render the checkout form (GET) or create the order + holds (POST)."""
    if request.method == "GET":
        zones = ShippingZone.objects.filter(is_active=True).order_by("name")
        return render(
            request,
            "storefront/checkout.html",
            {"zones": zones, "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY},
        )
    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body."}, status=400)

    try:
        quantities = _parse_checkout_items(data.get("items"))
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)

    contact_name = str(data.get("customer_name", "")).strip()
    contact_email = str(data.get("email", "")).strip()
    if not contact_name or not contact_email:
        return JsonResponse({"error": "Name and email are required."}, status=400)

    try:
        zone = ShippingZone.objects.get(id=data.get("zone_id"), is_active=True)
    except ShippingZone.DoesNotExist, ValueError, TypeError:
        return JsonResponse({"error": "Choose a valid shipping zone."}, status=400)

    # Guests need a session so their holds can be traced before the order pays.
    if not request.session.session_key:
        request.session.create()

    try:
        with transaction.atomic():
            variants = {
                variant.pk: variant
                for variant in ProductVariant.objects.select_related("product").filter(
                    pk__in=quantities
                )
            }
            missing = set(quantities) - set(variants)
            if missing:
                raise ValueError("Some cart items no longer exist — refresh your cart.")

            # Effective price honors variant overrides (never raw base_price),
            # and totals are correct at INSERT time so the DB reconciliation
            # check (total = subtotal + shipping) holds from the first write.
            subtotal = sum(variants[vid].price * qty for vid, qty in quantities.items())
            order = Order.objects.create(
                order_no=next_order_no(),
                customer=request.user if request.user.is_authenticated else None,
                subtotal=subtotal,
                shipping_fee=zone.fee,
                total=subtotal + zone.fee,
                shipping_address={
                    "name": contact_name,
                    "email": contact_email,
                    "phone": str(data.get("phone", "")).strip(),
                    "address_line1": str(data.get("address_line1", "")).strip(),
                    "city": str(data.get("city", "")).strip(),
                    "zone": zone.name,
                },
            )

            for variant_id, qty in quantities.items():
                # Raising inside the atomic block rolls EVERYTHING back — no
                # half-built orders, no stranded holds (Invariant 1).
                reserve_stock(
                    variant_id=variant_id,
                    qty=qty,
                    session_key=request.session.session_key or "",
                    order=order,
                )
                OrderItem.objects.create(
                    order=order,
                    variant=variants[variant_id],
                    qty=qty,
                    unit_price_snapshot=variants[variant_id].price,
                )
    except InsufficientStock as error:
        logger.info("Checkout rejected: %s", error)
        return JsonResponse(
            {"error": "Some items just sold out. Review your cart and try again."}, status=409
        )
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)

    token = Signer().sign(str(order.pk))
    success_url = request.build_absolute_uri(reverse("storefront:checkout-success", args=[token]))
    cancel_url = request.build_absolute_uri(reverse("storefront:cart"))

    try:
        checkout_url, _ = create_checkout_session(order, success_url, cancel_url)
    except (PayMongoError, Exception) as error:  # noqa: BLE001 — provider boundary
        # The order committed but no payment session exists: release the holds
        # immediately instead of stranding them for the 15-minute TTL.
        logger.error("Checkout session failed for %s: %s", order.order_no, error)
        for reservation in order.reservations.filter(status="active"):
            release_reservation(reservation.pk)
        return JsonResponse(
            {"error": "Payment provider is unavailable right now — please try again."},
            status=502,
        )

    return JsonResponse({"success": True, "checkout_url": checkout_url})


def checkout_success(request, token):
    """Post-payment landing page, reachable only through the signed token.

    The raw order number never appears in this URL: order numbers are
    sequential and guessable, and this page shows PII from the checkout
    snapshot.
    """
    signer = Signer()
    try:
        order_id = signer.unsign(token)
    except BadSignature:
        raise Http404 from None

    try:
        order = Order.objects.prefetch_related("items__variant__product").get(pk=order_id)
    except Order.DoesNotExist:
        raise Http404 from None

    # Development-only sandbox completion (ADR: MOCK_PAYMENTS). Production and
    # staging refuse to boot with this flag on; the webhook is the only real
    # confirmation path (Invariant 3).
    if settings.MOCK_PAYMENTS and request.GET.get("mock") == "1":
        if confirm_order_paid(order=order):
            order.refresh_from_db()
            try:
                status_url = request.build_absolute_uri(
                    reverse("storefront:order-status", args=[token])
                )
                send_order_confirmation(order, status_url)
                phone = order.shipping_address.get("phone")
                if phone:
                    send_sms(
                        phone,
                        f"MetroDrip: order {order.order_no} is paid. Track: {status_url}",
                    )
            except Exception:
                logger.exception("Mock-payment notifications failed for %s", order.order_no)

    return render(
        request,
        "storefront/checkout_success.html",
        {"order": order, "token": token},
    )


# ---------------------------------------------------------------------------
# D-4: Tokenized order status
# ---------------------------------------------------------------------------


# The happy-path fulfillment sequence rendered as a timeline; cancelled and
# refunded orders show only their terminal badge instead.
_PROGRESS_STEPS = ["pending", "paid", "packed", "shipped", "delivered"]


@require_GET
def order_status(request, token):
    """Read-only order status behind the signed token from the email link."""
    try:
        order_id = Signer().unsign(token)
    except BadSignature:
        raise Http404 from None

    try:
        order = (
            Order.objects.select_related("payment", "shipment")
            .prefetch_related("items__variant__product")
            .get(pk=order_id)
        )
    except Order.DoesNotExist:
        raise Http404 from None

    steps = None
    if order.status in _PROGRESS_STEPS:
        current = _PROGRESS_STEPS.index(order.status)
        steps = [
            {
                "label": label.title(),
                "state": "done" if index < current else "current" if index == current else "todo",
            }
            for index, label in enumerate(_PROGRESS_STEPS)
        ]

    return render(request, "storefront/order_status.html", {"order": order, "steps": steps})


# ---------------------------------------------------------------------------
# G-5: Contact form
# ---------------------------------------------------------------------------


def contact_page(request):
    """Render and process the contact form (FR-18: stored + emailed to staff)."""
    if request.method == "POST":
        name = str(request.POST.get("name", "")).strip()
        email = str(request.POST.get("email", "")).strip()
        message = str(request.POST.get("message", "")).strip()

        if not (name and email and message):
            return render(
                request,
                "storefront/contact.html",
                {"error": "All fields are required.", "form_values": request.POST},
            )

        contact_message = ContactMessage.objects.create(name=name, email=email, message=message)
        try:
            send_contact_alert(contact_message)
        except Exception:
            # Storage is the requirement; the email leg degrades gracefully.
            logger.exception("Contact alert email failed for message %s", contact_message.pk)
        return render(request, "storefront/contact.html", {"success": True})

    return render(request, "storefront/contact.html")


# ---------------------------------------------------------------------------
# Legacy: staging seed preview (superseded by the storefront; still gated)
# ---------------------------------------------------------------------------


def staging_seed_preview(request):
    """Render the deterministic seed through a read-only staging gate."""
    if not settings.STAGING_SEED_PREVIEW_ENABLED:
        raise Http404
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    products = list(
        Product.objects.filter(is_active=True)
        .select_related("category")
        .annotate(variant_count=Count("variants"))
        .order_by("name")
    )
    return render(
        request,
        "staging/seed_preview.html",
        {
            "products": products,
            "product_count": len(products),
            "total_variants": sum(product.variant_count for product in products),
        },
    )
