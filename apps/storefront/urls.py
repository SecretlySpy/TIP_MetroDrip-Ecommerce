"""Storefront URL patterns (C-2/C-3/C-4).

Public-facing routes for the shop listing, product detail, cart page, and the
cart availability API endpoint. The homepage lives at the root.
"""

from django.urls import path

from . import views

app_name = "storefront"

urlpatterns = [
    path("", views.homepage, name="home"),
    path("shop/", views.shop_listing, name="shop"),
    path("shop/<slug:slug>/", views.product_detail, name="product-detail"),
    path("checkout/", views.checkout_page, name="checkout"),
    # FR-13: Places province/city → ShippingZone (dropdown remains fallback).
    path("api/shipping/resolve-zone/", views.resolve_shipping_zone, name="resolve-zone"),
    # Signed token, never the raw order number — order numbers are sequential
    # and this page renders checkout PII.
    path("checkout/success/<str:token>/", views.checkout_success, name="checkout-success"),
    path("order/<str:token>/", views.order_status, name="order-status"),
    # FR-19: printable customer invoice, same signed token as the status page.
    path("order/<str:token>/invoice/", views.order_invoice, name="order-invoice"),
    path("cart/", views.cart_page, name="cart"),
    path("api/cart/availability/", views.cart_availability, name="cart-availability"),
    path("contact/", views.contact_page, name="contact"),
    path("developers/", views.developers_page, name="developers"),
]
