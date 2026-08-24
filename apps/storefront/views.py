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
from django.db.models import Count
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET
from django.views.decorators.vary import vary_on_cookie

from apps.accounts.models import WishlistItem
from apps.catalog.models import Fit, Product, Size
from apps.catalog.services import (
    get_all_categories,
    get_available_colors,
    get_catalog_queryset,
    get_product_detail,
)
from apps.cms.models import ContactMessage, HomepageBanner
from apps.core.money import format_centavos
from apps.inventory.services import (
    InsufficientStock,
    ReservationUnavailable,
    get_stock_records,
)
from apps.notifications.services import send_contact_alert, send_order_confirmation
from apps.notifications.sms import send_sms
from apps.orders.checkout import CheckoutError, PaymentSessionError, place_order
from apps.orders.models import Order
from apps.payments.services import confirm_order_paid
from apps.shipping.models import ShippingZone
from apps.shipping.zones import resolve_zone
from config.middleware import get_correlation_id

logger = logging.getLogger(__name__)


def _json_error(message, status=400, **extra):
    """Storefront JSON error envelope with correlation id (NFR-12)."""
    body = {"error": message, "correlation_id": get_correlation_id() or None}
    body.update(extra)
    return JsonResponse(body, status=status)


# ---------------------------------------------------------------------------
# C-2: Homepage
# ---------------------------------------------------------------------------


@require_GET
@cache_page(60 * 5)  # NFR-1: catalog pages are cacheable
@vary_on_cookie
def homepage(request):
    """Render the homepage with hero banners and the newest active products.

    `vary_on_cookie` is not optional here, and its position matters.

    This page renders base.html, whose navbar is per-user: "Log In" vs "Account",
    plus the staff console shortcut. `cache_page` is a *view* decorator, so it
    stores the response before `SessionMiddleware.process_response` gets a chance
    to add `Vary: Cookie` — the header does reach the browser, but it arrives too
    late to influence the cache key. One visitor's rendered navbar was therefore
    served to every other visitor for the next five minutes.

    Decorators apply bottom-up, so `vary_on_cookie` must sit *below* `cache_page`:
    on the way out it patches the Vary header first, and `cache_page` then reads
    that header when choosing the key.

    Anonymous visitors have no session cookie until something writes to the
    session, so they still share a single cache entry — the NFR-1 benefit is kept
    for the traffic that dominates this page.
    """
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

    # One stock read for the whole page. Looping `get_stock_record` here meant
    # one HTTP round trip per variant under INVENTORY_PROVIDER=service — around
    # 36 sequential calls on the seeded catalog, each with its own timeout.
    variants = list(product.variants.all())
    stock = get_stock_records([variant.pk for variant in variants])

    variants_data = [
        {
            "id": variant.pk,
            "sku": variant.sku,
            "size": variant.size,
            "color": variant.color,
            "fit": variant.fit,
            "price": variant.price,
            "price_display": format_centavos(variant.price),
            # An unstocked variant reads as zero, so it renders sold out rather
            # than sellable — the batch accessor guarantees a row for every id.
            "available": stock[variant.pk].available,
            "product_name": product.name,
        }
        for variant in variants
    ]

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
            return _json_error("Invalid variant IDs")
    elif request.method == "POST":
        try:
            body = json.loads(request.body)
            variant_ids = [int(x) for x in body.get("ids", [])]
        # All malformed JSON/list conversions share one public validation response.
        except (json.JSONDecodeError, ValueError, TypeError):
            return _json_error("Invalid request body")
    else:
        return HttpResponseNotAllowed(["GET", "POST"])

    if not variant_ids or len(variant_ids) > 50:
        return _json_error("Provide 1–50 variant IDs")

    # This endpoint accepts up to 50 ids; reading them one at a time was 50
    # sequential round trips under the service provider.
    stock = get_stock_records(variant_ids)
    availability = {str(variant_id): stock[variant_id].available for variant_id in variant_ids}

    return JsonResponse({"availability": availability})


# ---------------------------------------------------------------------------
# D-1/D-2: Checkout
# ---------------------------------------------------------------------------


@require_GET
def resolve_shipping_zone(request):
    """FR-13: JSON helper for Places → zone auto-select on web checkout.

    Query params: province (admin_area_level_1), city (optional).
    Returns {"zone_id", "zone_name", "fee", "fee_display"} or zone fields null.
    """
    province = str(request.GET.get("province", "")).strip()
    city = str(request.GET.get("city", "")).strip()
    zone = resolve_zone(province, city=city)
    if zone is None:
        return JsonResponse(
            {
                "zone_id": None,
                "zone_name": None,
                "fee": None,
                "fee_display": None,
                "correlation_id": get_correlation_id() or None,
            }
        )
    return JsonResponse(
        {
            "zone_id": zone.pk,
            "zone_name": zone.name,
            "fee": zone.fee,
            "fee_display": format_centavos(zone.fee),
            "correlation_id": get_correlation_id() or None,
        }
    )


def checkout_page(request):
    """Render the checkout form (GET) or create the order + holds (POST)."""
    if request.method == "GET":
        zones = ShippingZone.objects.filter(is_active=True).order_by("name")
        return render(
            request,
            "storefront/checkout.html",
            {
                "zones": zones,
                "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
                "payment_provider": settings.PAYMENT_PROVIDER,
            },
        )
    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error("Invalid request body.")

    # Guests need a session so their holds can be traced before the order pays.
    if not request.session.session_key:
        request.session.create()

    # place_order substitutes the signed status token once the order id exists,
    # so the redirect target is templated rather than built here (H-4).
    success_url = request.build_absolute_uri(
        reverse("storefront:checkout-success", args=["__TOKEN__"])
    )

    try:
        order, checkout_url = place_order(
            items=data.get("items"),
            zone_id=data.get("zone_id"),
            contact={
                "name": data.get("customer_name", ""),
                "email": data.get("email", ""),
                "phone": data.get("phone", ""),
                "address_line1": data.get("address_line1", ""),
                "city": data.get("city", ""),
            },
            customer=request.user if request.user.is_authenticated else None,
            session_key=request.session.session_key or "",
            success_url=success_url,
            cancel_url=request.build_absolute_uri(reverse("storefront:cart")),
        )
    except CheckoutError as error:
        return _json_error(str(error))
    except InsufficientStock as error:
        logger.info("Checkout rejected: %s", error)
        return _json_error("Some items just sold out. Review your cart and try again.", status=409)
    except ReservationUnavailable as error:
        # place_order already released the holds before raising.
        logger.error("Stock service unavailable during checkout: %s", error)
        return _json_error(
            "We could not confirm stock right now — please try again in a moment.",
            status=502,
        )
    except PaymentSessionError as error:
        # place_order already released the holds before raising.
        logger.error("Checkout session failed: %s", error)
        return _json_error(
            "Payment provider is unavailable right now — please try again.",
            status=502,
        )

    logger.info("Checkout created order_no=%s", order.order_no)

    return JsonResponse(
        {
            "success": True,
            "checkout_url": checkout_url,
            "correlation_id": get_correlation_id() or None,
        }
    )


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

    # Development-only sandbox completion (simulated provider). Production and
    # staging refuse to boot with this provider on; the webhook is the only real
    # confirmation path (Invariant 3).
    if (
        getattr(settings, "PAYMENT_PROVIDER", "paymongo") == "simulated"
        and request.GET.get("mock") == "1"
    ):
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


@require_GET
def order_invoice(request, token):
    """FR-19: printable customer invoice behind the same signed token.

    Guests reach it from their emailed link and account holders from order
    history, so the token — not a login — is what authorizes it (ADR-D-004).
    """
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

    return render(request, "storefront/invoice.html", {"order": order, "token": token})


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


# ---------------------------------------------------------------------------
# Developers / Team Profile (FR-20, course instruction #8)
# ---------------------------------------------------------------------------

TEAM_MEMBERS = [
    {
        "name": "Navarro, Arshad Edwin",
        "role": "Project Leader",
        "bio": "Full-stack architect responsible for systems integration strategy, "
        "sprint planning, and cross-team coordination. Leads the enterprise "
        "architecture alignment with course deliverables.",
        "contribution": "Architecture & Integration",
        "avatar": "team/navarro.jpg",
    },
    {
        "name": "Pameroyan, Archim Paul C.",
        "role": "Backend Developer",
        "bio": "Designed and implemented the inventory management system, checkout "
        "saga, and payment gateway integration. Owns the stock reservation "
        "engine and concurrency-safe transaction flows.",
        "contribution": "Inventory & Payments",
        "avatar": "team/pameroyan.jpg",
    },
    {
        "name": "De Borja, John Meickann M.",
        "role": "Frontend Developer",
        "bio": "Built the storefront UI using the MetroDrip design system with "
        "Django Templates, HTMX, and Alpine.js. Responsible for responsive "
        "layouts and WCAG AA accessibility compliance.",
        "contribution": "Storefront & UI/UX",
        "avatar": "team/deborja.jpg",
    },
    {
        "name": "Carlos, Reuel L.",
        "role": "QA & DevOps Engineer",
        "bio": "Manages the CI/CD pipeline, Docker containerization, and deployment "
        "infrastructure. Authors the test suite covering concurrency gates, "
        "checkout flows, and migration integrity.",
        "contribution": "Testing & Deployment",
        "avatar": "team/carlos.jpg",
    },
    {
        "name": "Nogoy, Marcus Dylan",
        "role": "Database & Security Engineer",
        "bio": "Designed the MySQL 8 schema with InnoDB invariants, wrote the "
        "migration verification suite, and implemented webhook signature "
        "verification and CSRF protections across all endpoints.",
        "contribution": "Database & Security",
        "avatar": "team/nogoy.jpg",
    },
]


@require_GET
def developers_page(request):
    """Render the team profile page (FR-20, course instruction #8)."""
    return render(request, "storefront/developers.html", {"team": TEAM_MEMBERS})
