"""Review submission (G-4, FR-17): verified purchasers only, always moderated."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.signing import Signer
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from apps.orders.models import Order, OrderStatus

from .models import Review, ReviewStatus


@login_required
@require_POST
def submit_review(request):
    order_no = request.POST.get("order_no", "")
    # Ownership is part of the lookup: another customer's order number 404s
    # rather than leaking whether it exists.
    order = get_object_or_404(Order, order_no=order_no, customer=request.user)
    product = get_object_or_404(Product, pk=request.POST.get("product_id"))

    # Orders have no token field — status-page redirects re-sign the id with
    # the same Signer the status view verifies.
    status_token = Signer().sign(str(order.pk))

    try:
        rating = int(request.POST.get("rating", ""))
    except TypeError, ValueError:
        rating = 0

    if order.status != OrderStatus.DELIVERED:
        messages.error(request, "You can only review items from delivered orders.")
    elif not 1 <= rating <= 5:
        messages.error(request, "Pick a rating from 1 to 5 stars.")
    elif not order.items.filter(variant__product=product).exists():
        messages.error(request, "That product is not part of this order.")
    else:
        _, created = Review.objects.update_or_create(
            customer=request.user,
            product=product,
            defaults={
                "order": order,
                "rating": rating,
                "body": str(request.POST.get("body", "")).strip(),
                # Edits re-enter moderation: nothing unapproved ever renders
                # publicly (M4.5 gate).
                "status": ReviewStatus.PENDING,
            },
        )
        if created:
            messages.success(request, "Review submitted — it will appear once approved.")
        else:
            messages.success(request, "Review updated — it will reappear once re-approved.")

    return redirect("storefront:order-status", token=status_token)
