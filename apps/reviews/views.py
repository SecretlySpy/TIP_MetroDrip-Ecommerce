"""Views for submitting reviews (G-4)."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages

from .models import Review
from apps.orders.models import Order, OrderStatus
from apps.catalog.models import Product

@login_required
@require_POST
def submit_review(request):
    order_no = request.POST.get("order_no")
    product_id = request.POST.get("product_id")
    rating = int(request.POST.get("rating", 0))
    body = request.POST.get("body", "")
    
    order = get_object_or_404(Order, order_no=order_no, customer=request.user)
    product = get_object_or_404(Product, id=product_id)
    
    if order.status != OrderStatus.DELIVERED:
        messages.error(request, "You can only review delivered items.")
        return redirect("storefront:order-status", token=order.token)
        
    if not (1 <= rating <= 5):
        messages.error(request, "Rating must be between 1 and 5.")
        return redirect("storefront:order-status", token=order.token)
        
    # Check if the product was actually in this order
    if not order.items.filter(variant__product=product).exists():
        messages.error(request, "Product not found in this order.")
        return redirect("storefront:order-status", token=order.token)
        
    review, created = Review.objects.update_or_create(
        customer=request.user,
        product=product,
        defaults={
            "order": order,
            "rating": rating,
            "body": body,
            "status": "pending"  # Needs moderation
        }
    )
    
    if created:
        messages.success(request, "Review submitted for moderation!")
    else:
        messages.success(request, "Review updated and pending moderation.")
        
    return redirect("storefront:order-status", token=order.token)
