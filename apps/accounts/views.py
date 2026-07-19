"""Customer account views (Epic G: registration, login, profile, wishlist,
order history, guest-order claiming)."""

import json
import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from apps.orders.models import Order

from .models import Customer, WishlistItem

logger = logging.getLogger(__name__)


def _safe_next_url(request):
    """Return a validated post-login redirect target, or None.

    `next` comes from the query string / form and must never leave this host —
    an unvalidated redirect would let a crafted login link bounce shoppers to
    an attacker's site with a plausible-looking MetroDrip URL.
    """
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return None


def register_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    if request.method == "POST":
        email = str(request.POST.get("email", "")).strip().lower()
        password = request.POST.get("password", "")
        name = str(request.POST.get("name", "")).strip()
        phone = str(request.POST.get("phone", "")).strip()

        if not email or not password or not name:
            return render(request, "accounts/register.html", {"error": "Missing required fields."})
        if Customer.objects.filter(email=email).exists():
            return render(request, "accounts/register.html", {"error": "Email already in use."})

        user = Customer.objects.create_user(email=email, password=password, name=name, phone=phone)
        login(request, user)

        # FR-15: guest orders with this email become claimable; auto-attach the
        # exact matches right away so history is complete on first login.
        claimed = 0
        for order in Order.objects.filter(customer__isnull=True, shipping_address__email=email):
            order.customer = user
            order.save(update_fields=["customer"])
            claimed += 1
        if claimed:
            messages.success(request, f"We attached {claimed} previous order(s) to your account.")

        return redirect("accounts:profile")

    return render(request, "accounts/register.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    if request.method == "POST":
        email = str(request.POST.get("email", "")).strip().lower()
        password = request.POST.get("password", "")

        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            return redirect(_safe_next_url(request) or "accounts:profile")
        return render(request, "accounts/login.html", {"error": "Invalid email or password."})

    return render(request, "accounts/login.html")


@require_POST
def logout_view(request):
    logout(request)
    return redirect("storefront:home")


@login_required
def profile_view(request):
    """View and update profile details (FR-14)."""
    if request.method == "POST":
        name = str(request.POST.get("name", "")).strip()
        phone = str(request.POST.get("phone", "")).strip()
        if not name:
            messages.error(request, "Name cannot be empty.")
        else:
            request.user.name = name
            request.user.phone = phone
            request.user.save(update_fields=["name", "phone"])
            messages.success(request, "Profile updated.")
        return redirect("accounts:profile")

    orders = Order.objects.filter(customer=request.user).order_by("-created_at")[:5]
    wishlist = WishlistItem.objects.filter(customer=request.user).select_related(
        "product", "product__category"
    )
    return render(
        request,
        "accounts/profile.html",
        {"recent_orders": orders, "wishlist": wishlist},
    )


@login_required
def order_history(request):
    orders = Order.objects.filter(customer=request.user).order_by("-created_at")
    return render(request, "accounts/order_history.html", {"orders": orders})


@login_required
@require_POST
def claim_guest_order(request):
    """Attach a guest order to the logged-in account when the emails match (FR-15)."""
    order_no = str(request.POST.get("order_no", "")).strip()
    try:
        order = Order.objects.get(order_no=order_no, customer__isnull=True)
    except Order.DoesNotExist:
        messages.error(request, "No unclaimed order with that number was found.")
        return redirect("accounts:order-history")

    if order.shipping_address.get("email", "").lower() == request.user.email.lower():
        order.customer = request.user
        order.save(update_fields=["customer"])
        messages.success(request, f"Order {order.order_no} is now attached to your account.")
    else:
        # Same message as not-found: never confirm that a guessed order number
        # exists but belongs to someone else's email.
        messages.error(request, "No unclaimed order with that number was found.")
    return redirect("accounts:order-history")


@login_required
@require_POST
def toggle_wishlist(request):
    """Add/remove a product from the wishlist (FR-16); returns the new state."""
    try:
        product_id = json.loads(request.body).get("product_id")
        product = Product.objects.get(pk=product_id)
    except json.JSONDecodeError, TypeError, ValueError, Product.DoesNotExist:
        return JsonResponse({"error": "Unknown product."}, status=400)

    item, created = WishlistItem.objects.get_or_create(customer=request.user, product=product)
    if not created:
        item.delete()
    return JsonResponse({"success": True, "added": created})
