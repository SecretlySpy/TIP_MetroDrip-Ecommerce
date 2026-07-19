"""Views for customer accounts (Epic G)."""

import json
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods, require_POST
from django.core.signing import Signer

from .models import Customer, WishlistItem
from apps.orders.models import Order
from apps.catalog.models import Product

def register_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")
        
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        name = request.POST.get("name")
        phone = request.POST.get("phone", "")
        
        if not email or not password or not name:
            return render(request, "accounts/register.html", {"error": "Missing required fields."})
            
        if Customer.objects.filter(email=email).exists():
            return render(request, "accounts/register.html", {"error": "Email already in use."})
            
        user = Customer.objects.create_user(email=email, password=password, name=name, phone=phone)
        login(request, user)
        return redirect("accounts:profile")
        
    return render(request, "accounts/register.html")

def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")
        
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get("next") or "accounts:profile"
            return redirect(next_url)
        else:
            return render(request, "accounts/login.html", {"error": "Invalid email or password."})
            
    return render(request, "accounts/login.html")

@require_POST
def logout_view(request):
    logout(request)
    return redirect("storefront:home")

@login_required
def profile_view(request):
    """View and update profile + saved addresses."""
    if request.method == "POST":
        # Handle updating info or addresses
        pass
        
    orders = Order.objects.filter(customer=request.user).order_by("-created_at")[:5]
    wishlist = WishlistItem.objects.filter(customer=request.user).select_related("product")
    
    return render(request, "accounts/profile.html", {
        "recent_orders": orders,
        "wishlist": wishlist
    })

@login_required
def order_history(request):
    orders = Order.objects.filter(customer=request.user).order_by("-created_at")
    return render(request, "accounts/order_history.html", {"orders": orders})

@login_required
@require_POST
def claim_guest_order(request):
    """Claim a guest order and attach it to the current user."""
    order_no = request.POST.get("order_no")
    try:
        order = Order.objects.get(order_no=order_no, customer__isnull=True)
        if order.shipping_address.get("email") == request.user.email:
            order.customer = request.user
            order.save(update_fields=["customer"])
    except Order.DoesNotExist:
        pass
    return redirect("accounts:order-history")

@login_required
@require_POST
def toggle_wishlist(request):
    try:
        data = json.loads(request.body)
        product_id = data.get("product_id")
        product = Product.objects.get(id=product_id)
        
        item, created = WishlistItem.objects.get_or_create(customer=request.user, product=product)
        if not created:
            item.delete()
            added = False
        else:
            added = True
            
        return JsonResponse({"success": True, "added": added})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
