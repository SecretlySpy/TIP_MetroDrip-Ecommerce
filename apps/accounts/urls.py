from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("orders/", views.order_history, name="order-history"),
    path("orders/claim/", views.claim_guest_order, name="claim-guest-order"),
    path("wishlist/toggle/", views.toggle_wishlist, name="toggle-wishlist"),
]
