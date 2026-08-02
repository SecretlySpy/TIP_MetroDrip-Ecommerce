"""Public mobile API v1 (D-12). Breaking changes ship as /v2 — never here."""

from django.urls import path

from . import views

app_name = "mobile_api"

urlpatterns = [
    # H-3: auth
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/refresh/", views.RefreshView.as_view(), name="refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/password-reset/", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "auth/password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    # H-2: catalog
    path("catalog/products/", views.ProductListView.as_view(), name="product-list"),
    path("catalog/products/<slug:slug>/", views.ProductDetailView.as_view(), name="product-detail"),
    path("catalog/categories/", views.CategoryListView.as_view(), name="category-list"),
    # H-4: cart + checkout
    path("cart/validate/", views.CartValidateView.as_view(), name="cart-validate"),
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path(
        "checkout/confirm-simulated/",
        views.SimulatedPaymentConfirmView.as_view(),
        name="checkout-confirm-simulated",
    ),
    path("shipping/zones/", views.ZoneListView.as_view(), name="zone-list"),
    # H-5: orders
    path("orders/", views.OrderListView.as_view(), name="order-list"),
    path("orders/track/<str:token>/", views.OrderTrackView.as_view(), name="order-track"),
    path("orders/<str:order_no>/", views.OrderDetailView.as_view(), name="order-detail"),
    # H-6: account, wishlist, reviews
    path("account/profile/", views.ProfileView.as_view(), name="profile"),
    path("wishlist/", views.WishlistView.as_view(), name="wishlist"),
    path("reviews/", views.ReviewCreateView.as_view(), name="review-create"),
    # H-10: devices + notification centre
    path("notifications/devices/", views.DeviceRegisterView.as_view(), name="device-register"),
    path("notifications/", views.NotificationListView.as_view(), name="notification-list"),
    path(
        "notifications/read-all/",
        views.NotificationReadAllView.as_view(),
        name="notification-read-all",
    ),
    path(
        "notifications/<int:pk>/read/",
        views.NotificationReadView.as_view(),
        name="notification-read",
    ),
]
