"""Root URL configuration.

Public storefront, webhook, and account routes are added by their own epics
(strict build order) — each app will expose an urls.py that gets included here.
"""

from django.contrib import admin
from django.urls import include, path

from apps.storefront.views import staging_seed_preview
from config.views import liveness, readiness

urlpatterns = [
    path("healthz/live/", liveness, name="healthz-live"),
    path("healthz/ready/", readiness, name="healthz-ready"),
    path("staging/seed/", staging_seed_preview, name="staging-seed-preview"),
    path("admin/", admin.site.urls),
    # Storefront routes (Epic C): homepage, shop, product detail, cart.
    # Included last so admin/health/staging paths take precedence.
    path("api/", include("apps.payments.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("pages/", include("django.contrib.flatpages.urls")),
    path("", include("apps.storefront.urls")),
]
